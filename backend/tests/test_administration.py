import hashlib
import json
import re
import uuid
from datetime import timedelta
import pytest
from django.core import mail
from django.db import IntegrityError, transaction
from django.test import Client
from django.utils import timezone
from core.models import (AuditLog, CompanyInvitation, CompanyModule, InvitationRole, Membership,
                         MembershipRole, Module, ModuleDependency, Role, User)
from core.services import create_company

pytestmark = pytest.mark.django_db


def post(client, path, body):
    token = client.get('/api/v1/auth/csrf/').json()['csrfToken']
    return client.post('/api/v1/' + path, data=json.dumps(body), content_type='application/json', HTTP_X_CSRFTOKEN=token)


@pytest.fixture
def owner():
    return User.objects.create_user('owner@example.com', 'Long-password!2026', full_name='Propriétaire', email_verified=True)


@pytest.fixture
def company(owner):
    return create_company(owner, uuid.uuid4(), {'name': 'Société A', 'country_code': 'GN', 'currency_code': 'GNF'})[0]


@pytest.fixture
def client(owner):
    client = Client(enforce_csrf_checks=True)
    client.force_login(owner)
    return client


def test_roles_assignment_and_last_admin(client, owner, company):
    base = f'companies/{company.id}/'
    created = post(client, base + 'roles/create/', {'name': 'Lecteur', 'permission_codes': ['company.view']})
    assert created.status_code == 201
    role_id = created.json()['id']
    member = Membership.objects.get(company=company, user=owner)
    assert post(client, base + f'members/{member.id}/roles/', {'role_ids': [role_id]}).status_code == 400
    assert member.membershiprole_set.filter(role__is_system=True).exists()
    admin = Role.objects.get(company=company, is_system=True)
    assert post(client, base + f'roles/{admin.id}/update/', {'name': 'Modifié', 'permission_codes': []}).status_code == 400
    assert post(client, base + f'roles/{role_id}/update/', {'name': 'Lecteur avancé', 'permission_codes': ['company.view', 'members.view']}).status_code == 200
    assert post(client, base + 'roles/create/', {'name': 'Lecteur avancé', 'permission_codes': []}).status_code == 400
    assert post(client, base + 'roles/create/', {'name': 'Inconnu', 'permission_codes': ['platform.root']}).status_code == 400


def test_invitation_acceptance_replay_wrong_email_and_revocation(settings, client, company):
    settings.EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
    role = Role.objects.get(company=company, is_system=True)
    base = f'companies/{company.id}/invitations/'
    response = post(client, base, {'email': 'invited@example.com', 'role_ids': [str(role.id)]})
    assert response.status_code == 201
    token = re.search(r'#token=([^\s]+)', mail.outbox[-1].body)[1]
    assert token not in response.content.decode()
    invite = CompanyInvitation.objects.get(pk=response.json()['id'])
    assert invite.token_hash == hashlib.sha256(token.encode()).hexdigest()
    assert post(client, 'invitations/accept/', {'token': token}).status_code == 403
    user = User.objects.create_user('invited@example.com', 'Long-password!2026', email_verified=True)
    target = Client(enforce_csrf_checks=True)
    target.force_login(user)
    assert post(target, 'invitations/accept/', {'token': token}).status_code == 200
    assert post(target, 'invitations/accept/', {'token': token}).status_code == 400
    assert MembershipRole.objects.filter(membership__user=user, role=role).count() == 1
    assert AuditLog.objects.filter(company=company, action='invitation.accepted').count() == 1
    response = post(client, base, {'email': 'another@example.com', 'role_ids': [str(role.id)]})
    old = re.search(r'#token=([^\s]+)', mail.outbox[-1].body)[1]
    url = base + response.json()['id'] + '/'
    assert post(client, url + 'resend/', {}).status_code == 200
    new = re.search(r'#token=([^\s]+)', mail.outbox[-1].body)[1]
    assert new != old
    assert post(target, 'invitations/accept/', {'token': old}).status_code == 400
    assert post(client, url + 'revoke/', {}).status_code == 200
    assert post(target, 'invitations/accept/', {'token': new}).status_code == 400


def test_cross_company_roles_and_endpoints(settings, client, owner, company):
    settings.EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
    other = User.objects.create_user('other-owner@example.com', 'Long-password!2026', email_verified=True)
    foreign = create_company(other, uuid.uuid4(), {'name': 'B', 'country_code': 'FR', 'currency_code': 'EUR'})[0]
    foreign_role = Role.objects.get(company=foreign)
    member = Membership.objects.get(company=company, user=owner)
    assert post(client, f'companies/{company.id}/members/{member.id}/roles/', {'role_ids': [str(foreign_role.id)]}).status_code == 400
    assert post(client, f'companies/{company.id}/invitations/', {'email': 'person@example.com', 'role_ids': [str(foreign_role.id)]}).status_code == 400
    for resource in ('permissions', 'modules', 'audit', 'sequences', 'settings', 'invitations'):
        assert client.get(f'/api/v1/companies/{foreign.id}/{resource}/').status_code == 403
    assert not CompanyInvitation.objects.exists()


def test_module_dependencies_and_history(client, company):
    prerequisite = Module.objects.create(code='test-base', name='Base', status='available')
    module = Module.objects.create(code='test-dependent', name='Dépendant', status='available')
    ModuleDependency.objects.create(module=module, required_module=prerequisite)
    base = f'companies/{company.id}/modules/'
    assert post(client, base + 'test-dependent/enable/', {}).status_code == 200
    assert CompanyModule.objects.filter(company=company, enabled=True, module__in=[module, prerequisite]).count() == 2
    assert post(client, base + 'test-base/disable/', {}).status_code == 400
    assert post(client, base + 'test-dependent/disable/', {}).status_code == 200
    assert post(client, base + 'test-base/disable/', {}).status_code == 200
    assert CompanyModule.objects.filter(company=company, module=module).exists()
    assert post(client, base + 'core/disable/', {}).status_code == 400
    planned = Module.objects.create(code='planned-test', name='À venir', status='planned')
    assert post(client, base + planned.code + '/enable/', {}).status_code == 400


def test_settings_profile_audit_and_sequences(client, company):
    base = f'companies/{company.id}/'
    data = {'name': 'Nouvelle raison sociale', 'sector': 'Services', 'address': 'Adresse réelle', 'phone': '+224000000', 'timezone': 'Africa/Conakry', 'locale': 'fr'}
    assert post(client, base + 'settings/', data).status_code == 200
    assert client.get('/api/v1/' + base + 'settings/').json()['timezone'] == 'Africa/Conakry'
    data['timezone'] = 'FuseauInconnu'
    assert post(client, base + 'settings/', data).status_code == 400
    assert post(client, 'auth/me/', {'full_name': 'Nouveau nom'}).status_code == 200
    assert client.get('/api/v1/' + base + 'audit/').json()['count'] >= 2
    sequences = client.get('/api/v1/' + base + 'sequences/').json()
    assert {row['document_type'] for row in sequences} == {'sales_order', 'purchase_order', 'delivery', 'receipt', 'invoice', 'credit_note', 'transfer', 'adjustment', 'payment'}


def test_password_reset_is_private_one_time_and_invalidates_sessions(settings, owner):
    settings.EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
    c = Client(enforce_csrf_checks=True)
    assert c.post('/api/v1/auth/password-reset/', {}).status_code == 403
    old = Client(enforce_csrf_checks=True)
    old.force_login(owner)
    assert post(c, 'auth/password-reset/', {'email': 'unknown@example.com'}).status_code == 202
    assert post(c, 'auth/password-reset/', {'email': owner.email}).status_code == 202
    assert len(mail.outbox) == 1
    uid, token = re.search(r'#uid=([^&]+)&token=([^\s]+)', mail.outbox[0].body).groups()
    payload = {'uid': uid, 'token': token, 'password': 'New-strong-password!2026'}
    assert post(c, 'auth/password-reset-confirm/', payload).status_code == 200
    assert post(c, 'auth/password-reset-confirm/', payload).status_code == 400
    assert old.get('/api/v1/auth/me/').status_code == 403
    assert post(c, 'auth/login/', {'email': owner.email, 'password': payload['password']}).status_code == 200


def test_password_reset_requests_are_limited_without_enumeration(settings, owner):
    settings.EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
    c = Client(enforce_csrf_checks=True)
    for _ in range(5):
        assert post(c, 'auth/password-reset/', {'email': owner.email}).status_code == 202
    assert len(mail.outbox) == 3


def test_expired_invitation_and_database_tenant_constraints(settings, client, owner, company):
    settings.EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
    role = Role.objects.get(company=company, is_system=True)
    response = post(client, f'companies/{company.id}/invitations/', {'email': 'expired@example.com', 'role_ids': [str(role.id)]})
    token = re.search(r'#token=([^\s]+)', mail.outbox[-1].body)[1]
    invitation = CompanyInvitation.objects.get(pk=response.json()['id'])
    invitation.expires_at = timezone.now() - timedelta(seconds=1)
    invitation.save()
    user = User.objects.create_user('expired@example.com', 'Long-password!2026', email_verified=True)
    target = Client(enforce_csrf_checks=True)
    target.force_login(user)
    assert post(target, 'invitations/accept/', {'token': token}).status_code == 400
    foreign = create_company(owner, uuid.uuid4(), {'name': 'Autre', 'country_code': 'FR', 'currency_code': 'EUR'})[0]
    with pytest.raises(IntegrityError), transaction.atomic():
        InvitationRole.objects.create(company=company, invitation=invitation, role=Role.objects.get(company=foreign))


def test_invitation_failure_rolls_back_without_membership(settings, client, company, monkeypatch):
    import core.administration
    def fail(*args, **kwargs):
        raise RuntimeError('SMTP indisponible')
    monkeypatch.setattr(core.administration, 'send_mail', fail)
    role = Role.objects.get(company=company)
    with pytest.raises(RuntimeError):
        post(client, f'companies/{company.id}/invitations/', {'email': 'failed@example.com', 'role_ids': [str(role.id)]})
    assert not CompanyInvitation.objects.exists()
    assert not AuditLog.objects.filter(action='invitation.created').exists()
