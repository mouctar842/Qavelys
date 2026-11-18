import json
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest
from django.db import close_old_connections
from django.test import Client

from core.administration import next_reference
from core.models import AuditLog, DocumentSequence, Membership, MembershipRole, Permission, Role, RolePermission, User
from core.services import create_company

pytestmark = pytest.mark.django_db


def post(client, path, data):
    token = client.get('/api/v1/auth/csrf/').json()['csrfToken']
    return client.post(path, data=json.dumps(data), content_type='application/json', HTTP_X_CSRFTOKEN=token)


@pytest.fixture
def workspace():
    user = User.objects.create_user('admin-readability@example.com', 'Long-password!2026', full_name='Administratrice test', email_verified=True)
    company = create_company(user, uuid4(), {'name': 'Entreprise lisible', 'country_code': 'FR', 'currency_code': 'EUR'})[0]
    client = Client(enforce_csrf_checks=True)
    client.force_login(user)
    return user, company, client, f'/api/v1/companies/{company.pk}/'


def test_permission_groups_use_real_catalog_and_preserve_unknown(workspace):
    _, _, client, base = workspace
    Permission.objects.create(code='extension.inspect', description='Consulter une extension')
    rows = client.get(base + 'permissions/').json()
    assert {row['code'] for row in rows} == set(Permission.objects.values_list('code', flat=True))
    assert next(row for row in rows if row['code'] == 'products.view')['module_name'] == 'Catalogue'
    assert next(row for row in rows if row['code'] == 'extension.inspect')['module_name'] == 'Autres autorisations'


def test_templates_idempotent_no_assignment_and_no_overwrite(workspace):
    _, company, client, base = workspace
    assignments = MembershipRole.objects.count()
    template = next(row for row in client.get(base + 'role-templates/').json() if row['code'] == 'sales')
    assert 'roles.manage' not in template['permission_codes']
    assert 'sales.order.confirm' not in template['permission_codes']
    first = post(client, base + 'role-templates/', {'code': 'sales'})
    second = post(client, base + 'role-templates/', {'code': 'sales'})
    assert (first.status_code, second.status_code) == (201, 200)
    assert first.json()['id'] == second.json()['id']
    role = Role.objects.get(pk=first.json()['id'])
    RolePermission.objects.filter(role=role).delete()
    assert post(client, base + 'role-templates/', {'code': 'sales'}).json()['permission_codes'] == []
    assert MembershipRole.objects.count() == assignments
    assert AuditLog.objects.filter(company=company, action='role.created').count() == 1
    assert post(client, base + 'role-templates/', {'code': ['sales']}).status_code == 400


def test_readonly_access_cannot_install_or_configure_and_no_cross_tenant(workspace):
    user, company, _, base = workspace
    reader = User.objects.create_user('reader-admin@example.com', 'Long-password!2026', email_verified=True)
    member = Membership.objects.create(user=reader, company=company)
    role = Role.objects.create(company=company, name='Lecture administration')
    MembershipRole.objects.create(company=company, membership=member, role=role)
    for code in ('company.view', 'roles.view', 'sequences.view', 'audit.view'):
        RolePermission.objects.create(role=role, permission_id=code)
    client = Client(enforce_csrf_checks=True); client.force_login(reader)
    assert client.get(base + 'role-templates/').status_code == 200
    assert post(client, base + 'role-templates/', {'code': 'stock'}).status_code == 403
    assert post(client, base + 'sequences/invoice/', {'prefix': 'NEW-'}).status_code == 403
    assert all(not row['can_edit'] for row in client.get(base + 'sequences/').json())
    foreign = create_company(user, uuid4(), {'name': 'Privée', 'country_code': 'FR', 'currency_code': 'EUR'})[0]
    foreign_base = f'/api/v1/companies/{foreign.pk}/'
    for suffix in ('permissions/', 'role-templates/', 'audit/', 'sequences/'):
        assert client.get(foreign_base + suffix).status_code == 403
    assert post(client, foreign_base + 'role-templates/', {'code': 'employee'}).status_code == 403
    assert post(client, foreign_base + 'sequences/invoice/', {'prefix': 'NEW-'}).status_code == 403


def test_sequence_configuration_preserves_counter_and_locks_after_issue(workspace):
    _, company, client, base = workspace
    response = post(client, base + 'sequences/invoice/', {'prefix': 'FACT-2026-'})
    assert response.status_code == 200
    assert response.json()['preview'] == 'FACT-2026-000001'
    event = client.get(base + 'audit/', {'search': 'Factures clients'}).json()['results'][0]
    assert event['changes'] == [{'label': 'Préfixe', 'before': 'FAC-', 'after': 'FACT-2026-'}]
    row = next(row for row in client.get(base + 'sequences/').json() if row['document_type'] == 'invoice')
    assert row['label'] == 'Factures clients'
    assert row['module_name'] == 'Facturation'
    assert next_reference(company, 'invoice') == 'FACT-2026-000001'
    assert post(client, base + 'sequences/invoice/', {'prefix': 'OTHER-'}).status_code == 400
    assert next_reference(company, 'invoice') == 'FACT-2026-000002'
    assert AuditLog.objects.filter(action='sequences.updated', company=company).count() == 1


@pytest.mark.parametrize('data', [{'prefix': 'INVALID SPACE'}, {'prefix': '../'}, {'prefix': 'X-', 'next_number': 1}])
def test_sequence_rejects_bad_prefix_or_counter_write(workspace, data):
    _, company, client, base = workspace
    assert post(client, base + 'sequences/invoice/', data).status_code == 400
    assert DocumentSequence.objects.get(company=company, document_type='invoice').prefix == 'FAC-'


def test_audit_readable_changes_search_filters_and_historical_integrity(workspace):
    user, company, client, base = workspace
    first = AuditLog.objects.create(company=company, actor=user, action='sales.order_confirm', entity_type='SalesOrder', entity_id=uuid4(), before_data={'status': 'draft'}, after_data={'reference': 'CMD-000042', 'status': 'confirmed'})
    original = first.before_data.copy(), first.after_data.copy(), first.action
    response = client.get(base + 'audit/', {'search': 'Confirmation', 'module': 'sales', 'actor': str(user.pk), 'start': '2026-01-01', 'end': '2099-12-31'})
    assert response.status_code == 200
    assert response['Cache-Control'] == 'private, no-store'
    data = response.json()
    assert data['count'] == 1
    row = data['results'][0]
    assert row['target_label'] == 'CMD-000042'
    assert row['company_name'] == company.name
    assert {'label': 'Statut', 'before': 'Brouillon', 'after': 'Confirmé'} in row['changes']
    assert client.get(base + 'audit/', {'search': user.full_name}).json()['count'] >= 1
    assert client.get(base + 'audit/', {'search': 'CMD-000042'}).json()['count'] == 1
    assert client.get(base + 'audit/', {'start': 'not-a-date'}).status_code == 400
    assert client.get(base + 'audit/', {'actor': 'not-a-uuid'}).status_code == 400
    first.refresh_from_db()
    assert (first.before_data, first.after_data, first.action) == original
    foreign = create_company(user, uuid4(), {'name': 'Autre société', 'country_code': 'FR', 'currency_code': 'EUR'})[0]
    AuditLog.objects.create(company=foreign, actor=user, action='sales.order_confirm', entity_type='SalesOrder', entity_id=uuid4(), after_data={'reference': 'FOREIGN-SECRET'})
    assert client.get(base + 'audit/', {'search': 'FOREIGN-SECRET'}).json()['count'] == 0


@pytest.mark.django_db(transaction=True)
def test_concurrent_template_installation_does_not_duplicate(workspace):
    user, company, _, base = workspace
    barrier = Barrier(2)
    def run(_):
        close_old_connections()
        try:
            client = Client(enforce_csrf_checks=True)
            client.force_login(User.objects.get(pk=user.pk))
            barrier.wait(timeout=15)
            response = post(client, base + 'role-templates/', {'code': 'accountant'})
            return response.status_code, response.json()['id']
        finally:
            close_old_connections()
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(run, range(2)))
    assert sorted(status for status, _ in results) == [200, 201]
    assert len({key for _, key in results}) == 1
    assert Role.objects.filter(company=company, name='Comptable').count() == 1
