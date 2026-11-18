import json
import re
import uuid
import pytest
from django.core import mail
from django.db import IntegrityError, transaction
from django.test import Client
from core.models import AuditLog, Company, CompanySettings, Membership, MembershipRole, Role, RolePermission, User
from core.services import create_company, permissions_for

pytestmark = pytest.mark.django_db


@pytest.fixture
def user():
    return User.objects.create_user('alice@example.com', 'Long-password!2026', full_name='Alice', email_verified=True)


@pytest.fixture
def client(user):
    client = Client(enforce_csrf_checks=True)
    client.force_login(user)
    return client


def post(client, url, data, **headers):
    token = client.get('/api/v1/auth/csrf/').json()['csrfToken']
    return client.post(url, data=json.dumps(data), content_type='application/json', HTTP_X_CSRFTOKEN=token, **headers)


def company(user, name='Entreprise A'):
    return create_company(user, uuid.uuid4(), {'name': name, 'country_code': 'FR', 'currency_code': 'EUR'})[0]


def test_registration_verification_login_logout(settings):
    settings.EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
    c = Client(enforce_csrf_checks=True)
    body = {'email': 'ALICE@example.com', 'full_name': 'Alice', 'password': 'Long-password!2026'}
    assert c.post('/api/v1/auth/register/', body).status_code == 403
    assert post(c, '/api/v1/auth/register/', body).status_code == 202
    assert c.get('/api/v1/auth/me/').status_code == 403
    assert len(mail.outbox) == 1
    credentials = {k: body[k] for k in ('email', 'password')}
    pending = post(c, '/api/v1/auth/login/', credentials)
    assert pending.status_code == 403
    assert pending.json()['code'] == 'email_not_verified'
    token = re.search(r'token=([^\s]+)', mail.outbox[0].body)[1]
    assert post(c, '/api/v1/auth/verify-email/', {'token': token}).status_code == 200
    assert post(c, '/api/v1/auth/verify-email/', {'token': token}).status_code == 400
    assert post(c, '/api/v1/auth/login/', credentials).status_code == 200
    assert c.get('/api/v1/auth/me/').status_code == 200
    assert post(c, '/api/v1/auth/logout/', {}).status_code == 200
    assert c.get('/api/v1/auth/me/').status_code == 403


def test_login_throttle(user):
    c = Client(enforce_csrf_checks=True)
    for _ in range(5):
        assert post(c, '/api/v1/auth/login/', {'email': user.email, 'password': 'wrong'}).status_code == 400
    assert post(c, '/api/v1/auth/login/', {'email': user.email, 'password': 'Long-password!2026'}).status_code == 429


def test_csrf_origin_is_checked_through_same_origin_proxy(user):
    c = Client(enforce_csrf_checks=True)
    credentials = {'email': user.email, 'password': 'Long-password!2026'}
    assert post(c, '/api/v1/auth/login/', credentials, HTTP_HOST='localhost:5173', HTTP_ORIGIN='http://evil.example').status_code == 403
    assert post(c, '/api/v1/auth/login/', credentials, HTTP_HOST='localhost:5173', HTTP_ORIGIN='http://localhost:5173').status_code == 200


def test_create_company_idempotency_and_bootstrap(client, user):
    key = str(uuid.uuid4())
    body = {'name': 'Qavelys', 'country_code': 'FR', 'currency_code': 'EUR'}
    first = post(client, '/api/v1/companies/', body, HTTP_IDEMPOTENCY_KEY=key)
    second = post(client, '/api/v1/companies/', body, HTTP_IDEMPOTENCY_KEY=key)
    assert first.status_code == 201
    assert second.status_code == 200
    assert first.json()['id'] == second.json()['id']
    assert Company.objects.count() == CompanySettings.objects.count() == 1
    assert 'members.manage' in permissions_for(Membership.objects.get(user=user))
    assert AuditLog.objects.filter(action='company.created').count() == 1
    body['name'] = 'Autre'
    assert post(client, '/api/v1/companies/', body, HTTP_IDEMPOTENCY_KEY=key).status_code == 400
    body['name'] = 'Qavelys'
    Membership.objects.filter(user=user).update(status='suspended')
    assert post(client, '/api/v1/companies/', body, HTTP_IDEMPOTENCY_KEY=key).status_code == 403


def test_company_creation_rolls_back(user, monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError('échec simulé')
    monkeypatch.setattr(AuditLog.objects, 'create', fail)
    with pytest.raises(RuntimeError):
        company(user)
    assert not Company.objects.exists()
    assert not Membership.objects.exists()


def test_cross_tenant_and_suspended_membership(client, user):
    a = company(user)
    other = User.objects.create_user('other@example.com', 'password', email_verified=True)
    b = company(other, 'Entreprise B')
    assert [x['id'] for x in client.get('/api/v1/companies/').json()] == [str(a.id)]
    for resource in ('context', 'members', 'roles'):
        assert client.get(f'/api/v1/companies/{b.id}/{resource}/').status_code == 403
    target = Membership.objects.get(company=b)
    assert post(client, f'/api/v1/companies/{a.id}/members/{target.id}/suspend/', {}).status_code == 404
    Membership.objects.filter(company=a).update(status='suspended')
    assert client.get(f'/api/v1/companies/{a.id}/context/').status_code == 403


def test_permissions_are_required(client, user):
    a = company(user)
    RolePermission.objects.filter(role__company=a, permission_id='members.view').delete()
    assert client.get(f'/api/v1/companies/{a.id}/members/').status_code == 403


def test_last_admin_and_suspension(client, user):
    a = company(user)
    admin = Membership.objects.get(company=a)
    assert post(client, f'/api/v1/companies/{a.id}/members/{admin.id}/suspend/', {}).status_code == 400
    other = User.objects.create_user('employee@example.com', 'password')
    member = Membership.objects.create(company=a, user=other)
    for _ in range(2):
        assert post(client, f'/api/v1/companies/{a.id}/members/{member.id}/suspend/', {}).status_code == 200
    assert AuditLog.objects.filter(action='membership.suspended').count() == 1


def test_database_rejects_cross_tenant_roles(user):
    a = company(user)
    b = company(user, 'B')
    with pytest.raises(IntegrityError), transaction.atomic():
        MembershipRole.objects.create(company=a, membership=Membership.objects.get(company=a), role=Role.objects.get(company=b))


def test_multiple_companies_and_no_platform_bypass(client, user):
    a, b = company(user), company(user, 'B')
    assert len(client.get('/api/v1/companies/').json()) == 2
    for item in (a, b):
        assert client.get(f'/api/v1/companies/{item.id}/context/').status_code == 200
    user.is_superuser = True
    user.save()
    Membership.objects.filter(company=b).update(status='suspended')
    assert client.get(f'/api/v1/companies/{b.id}/context/').status_code == 403
