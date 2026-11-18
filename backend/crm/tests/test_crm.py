import json
import uuid
from datetime import timedelta
import pytest
from django.db import IntegrityError, transaction
from django.test import Client
from django.utils import timezone
from core.models import AuditLog, CompanyModule, Membership, Module, RolePermission, User
from core.services import create_company
from crm.models import CRMActivity, Lead
from reference.models import Partner

pytestmark = pytest.mark.django_db


def post(client, path, data):
    token = client.get('/api/v1/auth/csrf/').json()['csrfToken']
    return client.post('/api/v1/' + path, data=json.dumps(data), content_type='application/json', HTTP_X_CSRFTOKEN=token)


@pytest.fixture
def setup():
    user = User.objects.create_user('crm-owner@example.com', 'Long-password!2026', full_name='Commercial', email_verified=True)
    company = create_company(user, uuid.uuid4(), {'name': 'CRM A', 'country_code': 'GN', 'currency_code': 'GNF'})[0]
    other = create_company(user, uuid.uuid4(), {'name': 'CRM B', 'country_code': 'FR', 'currency_code': 'EUR'})[0]
    module, _ = Module.objects.get_or_create(code='crm', defaults={'name': 'CRM', 'status': 'available'})
    module.status = 'available'; module.save()
    for current in (company, other): CompanyModule.objects.create(company=current, module=module, enabled=True)
    contacts, _ = Module.objects.get_or_create(code='contacts', defaults={'name': 'Contacts', 'status': 'available'})
    for current in (company, other): CompanyModule.objects.get_or_create(company=current, module=contacts, defaults={'enabled': True})
    client = Client(enforce_csrf_checks=True); client.force_login(user)
    return client, user, company, other


def test_lead_move_persists_and_sensitive_patch_is_ignored(setup):
    client, _, company, _ = setup
    base = f'companies/{company.id}/crm/'
    response = post(client, base + 'leads/', {'title': 'Opportunité', 'expected_revenue': '1000.125000', 'probability': 35, 'stage': 'won'})
    assert response.status_code == 201 and response.json()['stage'] == 'new'
    lead_id = response.json()['id']
    assert post(client, base + f'leads/{lead_id}/move/', {'stage': 'qualified'}).json()['stage'] == 'qualified'
    assert client.get('/api/v1/' + base + 'leads/?stage=qualified').json()['count'] == 1
    assert Lead.objects.get(pk=lead_id).stage == 'qualified'
    assert post(client, base + f'leads/{lead_id}/move/', {'stage': 'invalid'}).status_code == 400
    assert post(client, base + f'leads/{lead_id}/update/', {'probability': 101}).status_code == 400


def test_relations_and_cross_tenant_ids_are_refused(setup):
    client, user, company, other = setup
    base = f'companies/{company.id}/crm/'
    foreign = Partner.objects.create(company=other, name='Contact extérieur')
    foreign_member = Membership.objects.get(company=other, user=user)
    assert post(client, base + 'leads/', {'title': 'Refus', 'partner_id': str(foreign.id)}).status_code == 400
    assert post(client, base + 'leads/', {'title': 'Refus', 'owner_id': str(foreign_member.id)}).status_code == 400
    lead = Lead.objects.create(company=other, owner=foreign_member, title='Extérieur')
    assert client.get('/api/v1/' + base + f'leads/{lead.id}/').status_code == 404
    with pytest.raises(IntegrityError), transaction.atomic():
        Lead.objects.create(company=company, owner=foreign_member, title='Contrainte SQL')


def test_customer_conversion_is_atomic_and_idempotent(setup):
    client, _, company, _ = setup
    base = f'companies/{company.id}/crm/'
    lead = post(client, base + 'leads/', {'title': 'Contrat de services'}).json()
    payload = {'name': 'Client prospect', 'email': 'customer@example.com'}
    first = post(client, base + f'leads/{lead["id"]}/convert-customer/', payload)
    second = post(client, base + f'leads/{lead["id"]}/convert-customer/', payload)
    assert first.status_code == second.status_code == 200
    assert first.json()['partner_id'] == second.json()['partner_id']
    assert Partner.objects.filter(company=company).count() == 1
    assert AuditLog.objects.filter(action='contacts.created_from_lead').count() == 1


def test_activity_validation_replay_and_history(setup):
    client, _, company, _ = setup
    base = f'companies/{company.id}/crm/'
    lead = post(client, base + 'leads/', {'title': 'Prospect'}).json()
    response = post(client, base + 'activities/', {'lead_id': lead['id'], 'type': 'call', 'due_at': (timezone.now() + timedelta(days=1)).isoformat(), 'description': 'Contacter le prospect', 'status': 'done'})
    assert response.status_code == 201 and response.json()['status'] == 'planned'
    activity_id = response.json()['id']
    for _ in range(2): assert post(client, base + f'activities/{activity_id}/complete/', {}).status_code == 200
    assert CRMActivity.objects.get(pk=activity_id).status == 'done'
    assert AuditLog.objects.filter(action='crm.activity_complete').count() == 1
    assert post(client, base + f'activities/{activity_id}/update/', {'description': 'Altération'}).status_code == 400
    history = client.get('/api/v1/' + base + f'leads/{lead["id"]}/history/').json()
    assert history['count'] == 3


def test_module_and_permission_gates(setup):
    client, _, company, _ = setup
    base = f'companies/{company.id}/crm/'
    RolePermission.objects.filter(role__company=company, permission_id='crm.manage').delete()
    assert post(client, base + 'leads/', {'title': 'Refusé'}).status_code == 403
    CompanyModule.objects.filter(company=company, module__code='crm').update(enabled=False)
    assert client.get('/api/v1/' + base + 'leads/').status_code == 403


def test_customer_conversion_requires_contacts_permission(setup):
    client, _, company, _ = setup
    base = f'companies/{company.id}/crm/'
    lead = post(client, base + 'leads/', {'title': 'Conversion protégée'}).json()
    RolePermission.objects.filter(role__company=company, permission_id='contacts.manage').delete()
    assert post(client, base + f'leads/{lead["id"]}/convert-customer/', {'name': 'Interdit'}).status_code == 403
    assert not Partner.objects.filter(company=company).exists()
