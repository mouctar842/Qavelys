import io
import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import pytest
from PIL import Image, PngImagePlugin
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command, CommandError
from django.db import IntegrityError, connections, transaction
from django.test import Client
from rest_framework.exceptions import PermissionDenied, ValidationError
from core.administration import assign_roles
from core.models import AuditLog, CompanyLogo, CompanySettings, Membership, MembershipRole, PlatformAuditLog, Role, User
from core.platform_services import change_user
from core.services import create_company, require_membership, suspend_member

pytestmark = pytest.mark.django_db


def user(email, **flags):
    return User.objects.create_user(email, 'Test-password!2026', full_name=email.split('@')[0], email_verified=True, **flags)


def company(owner, name='Entreprise logo'):
    return create_company(owner, uuid.uuid4(), {'name': name, 'country_code': 'FR', 'currency_code': 'EUR'})[0]


def client_for(actor):
    client = Client(enforce_csrf_checks=True); client.force_login(actor); return client


def post(client, path, data):
    token = client.get('/api/v1/auth/csrf/').json()['csrfToken']
    return client.post(path, json.dumps(data), content_type='application/json', HTTP_X_CSRFTOKEN=token)


def image_file(format='PNG', size=(24, 18), color='red', metadata=False):
    output = io.BytesIO(); image = Image.new('RGB', size, color)
    info = PngImagePlugin.PngInfo(); info.add_text('Comment', 'Private source metadata')
    image.save(output, format=format, **({'pnginfo': info} if metadata else {}))
    return SimpleUploadedFile('../../untrusted-name.svg', output.getvalue(), content_type='image/svg+xml')


def upload(client, company_id, file):
    token = client.get('/api/v1/auth/csrf/').json()['csrfToken']
    return client.post(f'/api/v1/companies/{company_id}/logo/', {'logo': file}, HTTP_X_CSRFTOKEN=token)


@pytest.fixture
def setup(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path / 'private-media'
    owner = user('owner@example.invalid'); tenant = company(owner)
    return owner, tenant, client_for(owner)


def test_logo_normalized_private_and_versions_retained(setup):
    owner, tenant, client = setup
    response = upload(client, tenant.id, image_file(metadata=True))
    assert response.status_code == 201
    url = response.json()['logo_url']; first = CompanyLogo.objects.get()
    assert first.company_id == tenant.id and first.uploaded_by == owner
    assert 'untrusted-name' not in first.file.name and first.file.name.endswith('.png')
    content = client.get(url); assert content.status_code == 200
    assert content['Cache-Control'] == 'private, no-store' and 'Cookie' in content['Vary']
    assert content['X-Content-Type-Options'] == 'nosniff' and content['Content-Type'] == 'image/png'
    # Le client Django ferme déjà le FileResponse à la consommation de l’itérateur.
    pixels = b''.join(content.streaming_content)
    with Image.open(io.BytesIO(pixels)) as image:
        assert image.format == 'PNG' and image.size == (24, 18) and 'Comment' not in image.info
    assert client.get(f'/api/v1/companies/{tenant.id}/settings/').json()['logo_url'] == url
    assert client.get(f'/api/v1/companies/{tenant.id}/context/').json()['company']['logo_url'] == url
    assert client.get('/api/v1/companies/').json()[0]['logo_url'] == url
    second = upload(client, tenant.id, image_file('JPEG', (1200, 600), 'blue'))
    assert second.status_code == 201 and second.json()['logo_url'] != url
    assert CompanyLogo.objects.count() == 2 and first.file.storage.exists(first.file.name)
    assert client.get(url).status_code == 404
    current = CompanySettings.objects.get(company=tenant).logo
    assert (current.width, current.height) == (1024, 512)
    assert AuditLog.objects.filter(company=tenant, action='company.logo_uploaded').count() == 2


@pytest.mark.parametrize('kind', ['empty', 'svg', 'corrupt', 'oversize', 'dimensions', 'animation'])
def test_logo_rejects_invalid_without_changing_settings(setup, kind):
    _, tenant, client = setup
    if kind == 'dimensions': file = image_file(size=(4097, 1))
    elif kind == 'animation':
        output = io.BytesIO(); Image.new('RGB', (10, 10), 'red').save(output, format='WEBP', save_all=True, append_images=[Image.new('RGB', (10, 10), 'blue')], duration=100, loop=0)
        file = SimpleUploadedFile('animation.webp', output.getvalue())
    else:
        data = {'empty': b'', 'svg': b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>', 'corrupt': b'not an image', 'oversize': b'x' * (2 * 1024 * 1024 + 1)}[kind]
        file = SimpleUploadedFile('logo.png', data)
    assert upload(client, tenant.id, file).status_code == 400
    assert not CompanyLogo.objects.exists() and CompanySettings.objects.get(company=tenant).logo_id is None


def test_logo_access_csrf_and_composite_tenant_constraint(setup):
    owner, tenant, client = setup
    other_owner = user('other@example.invalid'); other = company(other_owner, 'Autre')
    assert client.post(f'/api/v1/companies/{tenant.id}/logo/', {'logo': image_file()}).status_code == 403
    assert upload(client, other.id, image_file()).status_code == 403
    url = upload(client, tenant.id, image_file()).json()['logo_url']
    stranger = client_for(other_owner)
    assert stranger.get(url).status_code == 403
    assert stranger.get(url.replace(str(tenant.id), str(other.id))).status_code == 404
    root = user('platform@example.invalid', is_staff=True, is_superuser=True)
    assert client_for(root).get(url).status_code == 403
    assert Client().get(url).status_code == 403
    asset = CompanyLogo.objects.get()
    with pytest.raises(IntegrityError), transaction.atomic():
        CompanySettings.objects.filter(company=other).update(logo=asset)
        with connections['default'].cursor() as cursor: cursor.execute('SET CONSTRAINTS ALL IMMEDIATE')
    member = Membership.objects.get(company=tenant, user=owner)
    member.status = 'suspended'; member.save()
    assert client.get(url).status_code == 403 and upload(client, tenant.id, image_file()).status_code == 403
    member.status = 'active'; member.save(); tenant.status = 'suspended'; tenant.save()
    assert client.get(url).status_code == 403


def test_logo_viewer_cannot_upload(setup):
    _, tenant, _ = setup
    viewer = user('viewer@example.invalid'); member = Membership.objects.create(company=tenant, user=viewer)
    from core.models import RolePermission
    role = Role.objects.create(company=tenant, name='Lecteur')
    RolePermission.objects.create(role=role, permission_id='company.view')
    MembershipRole.objects.create(company=tenant, membership=member, role=role)
    assert upload(client_for(viewer), tenant.id, image_file()).status_code == 403


@pytest.mark.parametrize('flags', [{}, {'is_staff': True}, {'is_superuser': True}])
def test_platform_requires_both_global_flags(flags):
    actor = user(f'{uuid.uuid4().hex}@example.invalid', **flags); client = client_for(actor)
    assert not client.get('/api/v1/auth/me/').json()['is_platform_admin']
    for endpoint in ('overview', 'companies', 'users', 'modules', 'audit'):
        assert client.get(f'/api/v1/platform/{endpoint}/').status_code == 403


def test_platform_lists_actions_audit_and_suspended_access(setup):
    owner, tenant, owner_client = setup
    root = user('root@example.invalid', is_staff=True, is_superuser=True); client = client_for(root)
    assert client.get('/api/v1/auth/me/').json()['is_platform_admin']
    assert client.get(f'/api/v1/companies/{tenant.id}/context/').status_code == 403
    response = client.get('/api/v1/platform/companies/?search=logo&page_size=1&ordering=-name')
    assert response.status_code == 200 and response.json()['count'] == 1
    assert response.json()['results'][0]['member_count'] == 1
    assert response['Cache-Control'] == 'private, no-store'
    users = client.get('/api/v1/platform/users/').json()
    assert 'password' not in json.dumps(users) and 'token' not in json.dumps(users)
    for endpoint in ('overview', 'modules', 'audit'):
        assert client.get(f'/api/v1/platform/{endpoint}/').status_code == 200
    assert client.get('/api/v1/platform/users/?ordering=password').status_code == 400
    assert client.get('/api/v1/platform/companies/?page=-1').status_code == 400
    assert client.get('/api/v1/platform/companies/?status=deleted').status_code == 400
    path = f'/api/v1/platform/companies/{tenant.id}/suspend/'
    assert client.post(path, {'reason': 'Contrôle demandé'}).status_code == 403
    assert post(client, path, {'reason': 'court'}).status_code == 400
    for _ in range(2): assert post(client, path, {'reason': 'Contrôle demandé'}).status_code == 200
    assert PlatformAuditLog.objects.filter(target_company=tenant).count() == 1
    assert owner_client.get(f'/api/v1/companies/{tenant.id}/context/').status_code == 403
    assert owner_client.get('/api/v1/companies/').json() == []
    assert post(client, path.replace('suspend', 'activate'), {'reason': 'Contrôle terminé'}).status_code == 200
    assert owner_client.get(f'/api/v1/companies/{tenant.id}/context/').status_code == 200
    assert client.get('/api/v1/platform/audit/?search=terminé').json()['count'] == 1


def add_admin(tenant, actor):
    member = Membership.objects.create(company=tenant, user=actor)
    role = Role.objects.get(company=tenant, is_system=True, name='Administrateur')
    MembershipRole.objects.create(company=tenant, membership=member, role=role)
    return member


def test_platform_user_guards_session_revocation_and_membership_guards(setup):
    owner, tenant, owner_client = setup
    root = user('root@example.invalid', is_staff=True, is_superuser=True); client = client_for(root)
    assert post(client, f'/api/v1/platform/users/{root.id}/deactivate/', {'reason': 'Test personnel'}).status_code == 400
    path = f'/api/v1/platform/users/{owner.id}/deactivate/'
    assert post(client, path, {'reason': 'Compte à suspendre'}).status_code == 400
    second = user('second@example.invalid'); second_member = add_admin(tenant, second)
    assert post(client, path, {'reason': 'Compte à suspendre', 'is_superuser': True}).status_code == 200
    owner.refresh_from_db(); assert not owner.is_active and not owner.is_superuser
    assert owner_client.get('/api/v1/auth/me/').status_code == 403
    with pytest.raises(PermissionDenied): require_membership(owner, tenant.id, 'company.view')
    with pytest.raises(ValidationError): suspend_member(second, tenant.id, second_member.id)
    reader = Role.objects.create(company=tenant, name='Sans accès')
    with pytest.raises(ValidationError): assign_roles(second, tenant.id, second_member.id, [reader.id])
    assert post(client, path.replace('deactivate', 'activate'), {'reason': 'Compte rétabli'}).status_code == 200
    assert post(client, path.replace('deactivate', 'activate'), {'reason': 'Compte rétabli'}).status_code == 200
    assert PlatformAuditLog.objects.filter(target_user=owner).count() == 2
    # Société suspendue : conservation des données mais réactivation refusée sans admin.
    tenant.status = 'suspended'; tenant.save()
    change_user(root, owner.id, False, 'Compte à suspendre')
    change_user(root, second.id, False, 'Compte à suspendre')
    assert post(client, f'/api/v1/platform/companies/{tenant.id}/activate/', {'reason': 'Test réactivation'}).status_code == 400
    root.is_active = False; root.save()
    assert client.get('/api/v1/platform/overview/').status_code == 403


def test_grant_command_is_explicit_idempotent_and_keeps_verification(settings):
    settings.DEBUG = True; settings.REQUIRE_EMAIL_VERIFICATION = False
    target = user('designated@example.invalid'); target.email_verified = False; target.save()
    for _ in range(2): call_command('grant_platform_admin', target.email, stdout=io.StringIO())
    target.refresh_from_db(); assert target.is_staff and target.is_superuser and not target.email_verified
    assert PlatformAuditLog.objects.filter(target_user=target).count() == 1
    with pytest.raises(CommandError): call_command('grant_platform_admin', 'absent@example.invalid')
    other = user('unverified@example.invalid'); other.email_verified = False; other.save()
    settings.DEBUG = False
    with pytest.raises(CommandError): call_command('grant_platform_admin', other.email)


@pytest.mark.django_db(transaction=True)
def test_concurrent_deactivation_keeps_one_company_admin():
    first = user('first@example.invalid'); second = user('second@example.invalid')
    tenant = company(first); add_admin(tenant, second)
    root = user('root@example.invalid', is_staff=True, is_superuser=True); barrier = Barrier(2)
    def run(pk):
        connections.close_all(); barrier.wait(timeout=10)
        try:
            change_user(root, pk, False, 'Contrôle concurrent')
            return 'changed'
        except ValidationError: return 'refused'
        finally: connections.close_all()
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(run, [first.id, second.id]))
    assert sorted(results) == ['changed', 'refused']
    assert User.objects.filter(pk__in=[first.id, second.id], is_active=True).count() == 1


@pytest.mark.django_db(transaction=True)
def test_concurrent_platform_admins_cannot_disable_each_other():
    first = user('root-a@example.invalid', is_staff=True, is_superuser=True)
    second = user('root-b@example.invalid', is_staff=True, is_superuser=True); barrier = Barrier(2)
    def run(pair):
        actor, target = pair; connections.close_all(); barrier.wait(timeout=10)
        try:
            change_user(actor, target.id, False, 'Contrôle concurrent')
            return 'changed'
        except (ValidationError, PermissionDenied): return 'refused'
        finally: connections.close_all()
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(run, [(first, second), (second, first)]))
    assert sorted(results) == ['changed', 'refused']
    assert User.objects.filter(is_active=True, is_staff=True, is_superuser=True).count() == 1
