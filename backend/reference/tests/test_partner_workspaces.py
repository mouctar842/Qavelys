from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import uuid
import pytest
from django.db import close_old_connections, connection
from django.utils import timezone
from django.test import Client
from core.models import AuditLog, CompanyModule, Role, RolePermission, User
from reference.models import Partner
from sales.tests.test_orders import setup, create, payload, action, post
from invoicing.tests.test_invoices import finance, save, invoice_body, credit_body, validate
from invoicing.tests.test_payments_pdf import payment, pay_action, batch

pytestmark = pytest.mark.django_db


def endpoint(company, partner):
    return f'/api/v1/companies/{company.pk}/reference/partners/{partner.pk}/'


def test_old_writer_can_omit_new_profile_columns(finance):
    _, _, company, _, _, _, _ = finance
    with connection.cursor() as cursor:
        cursor.execute('''INSERT INTO reference_partner
            (id, created_at, updated_at, company_id, name, email, phone, address, is_customer, is_supplier, status)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING customer_reference, supplier_reference, delivery_address, customer_notes, supplier_notes''',
            [uuid.uuid4(), timezone.now(), timezone.now(), company.pk, 'Ancien écrivain', '', '', '', True, False, 'active'])
        assert cursor.fetchone() == ('', '', '', '', '')


def test_profile_metadata_shared_identity_and_opposite_fields_preserved(finance):
    client, _, company, _, _, partner, _ = finance
    base = endpoint(company, partner)
    response = client.post(base + 'update/', {})
    assert response.status_code == 403  # CSRF reste obligatoire.
    updated = post(client, f'companies/{company.pk}/reference/partners/{partner.pk}/update/', {'customer_reference': 'CLI-42', 'delivery_address': 'Livraison Conakry', 'customer_notes': 'Appeler avant passage', 'supplier_reference': 'FOUR-7', 'supplier_notes': 'Retrait au dépôt'})
    assert updated.status_code == 200
    assert post(client, f'companies/{company.pk}/reference/partners/{partner.pk}/update/', {'is_supplier': True, 'supplier_notes': 'Retrait sur rendez-vous'}).status_code == 200
    partner.refresh_from_db()
    assert partner.customer_notes == 'Appeler avant passage' and partner.delivery_address == 'Livraison Conakry'
    assert partner.customer_reference == 'CLI-42' and partner.supplier_reference == 'FOUR-7'
    assert client.get(f'/api/v1/companies/{company.pk}/reference/partners/', {'search': 'CLI-42', 'kind': 'customer'}).json()['count'] == 1
    assert client.get(f'/api/v1/companies/{company.pk}/reference/partners/', {'kind': 'invalid'}).status_code == 400


def test_add_profile_reuses_id_repeated_requests_and_historical_order(finance):
    client, _, company, _, product, partner, location = finance
    order = create(client, company, payload(product, partner, location))
    partner.is_supplier = False; partner.save()
    before = Partner.objects.filter(company=company).count()
    route = f'companies/{company.pk}/reference/partners/{partner.pk}/profiles/'
    for _ in range(2):
        response = post(client, route, {'profile': 'supplier'})
        assert response.status_code == 200 and response.json()['id'] == str(partner.pk)
    assert Partner.objects.filter(company=company).count() == before
    assert AuditLog.objects.filter(company=company, entity_id=partner.pk, action='partners.updated').count() == 1
    assert client.get(f'/api/v1/companies/{company.pk}/sales/orders/{order["id"]}/').json()['partner_id'] == str(partner.pk)
    partner.status = 'archived'; partner.save()
    assert post(client, route, {'profile': 'supplier'}).status_code == 400


def test_activity_filtered_by_partner_company_profile_and_modules(finance):
    client, _, company, other, product, partner, location = finance
    first = create(client, company, payload(product, partner, location))
    another = Partner.objects.create(company=company, name='Autre client', is_customer=True)
    create(client, company, payload(product, another, location))
    route = endpoint(company, partner) + 'activity/'
    data = client.get(route, {'profile': 'customer', 'section': 'sales'}).json()
    assert data['count'] == 1 and data['results'][0]['id'] == first['id']
    assert client.get(route, {'profile': 'supplier', 'section': 'sales'}).status_code == 403
    assert client.get(route, {'profile': 'customer', 'page': 'invalid'}).status_code == 400
    assert client.get(endpoint(other, partner) + 'activity/', {'profile': 'customer'}).status_code == 404
    CompanyModule.objects.filter(company=company, module__code='sales').update(enabled=False)
    response = client.get(route, {'profile': 'customer'})
    assert 'sales' not in {row['code'] for row in response.json()['available_sections']}
    assert 'deliveries' not in {row['code'] for row in response.json()['available_sections']}
    assert client.get(route, {'profile': 'customer', 'section': 'sales'}).status_code == 403
    assert response['Cache-Control'] == 'private, no-store'


def test_real_customer_balances_after_allocation_and_credits(finance):
    client, _, company, _, _, partner, _ = finance
    invoice = save(client, company, invoice_body(partner, lines=[{'description': 'Service', 'quantity': '1', 'unit_price': '100'}]))
    assert validate(client, company, invoice).status_code == 200
    received, _ = payment(client, company, partner, '40')
    assert pay_action(client, company, received, 'allocate', batch((invoice, '40'))).status_code == 200
    credit = save(client, company, credit_body(invoice, '0.25'), 'credit-notes')
    assert validate(client, company, credit, 'credit-notes').status_code == 200
    data = client.get(endpoint(company, partner) + 'activity/', {'profile': 'customer', 'section': 'invoices'}).json()
    from decimal import Decimal
    assert Decimal(data['balances'][0]['amount_due']) == Decimal('35')
    credit2 = save(client, company, credit_body(invoice, '0.55'), 'credit-notes')
    assert validate(client, company, credit2, 'credit-notes').status_code == 200
    rows = client.get(endpoint(company, partner) + 'activity/', {'profile': 'customer'}).json()['balances']
    assert Decimal(rows[0]['amount_due']) == 0 and Decimal(rows[0]['credit_balance']) == 20


def test_permissions_do_not_leak_activity_or_financial_balances(finance):
    client, _, company, _, _, partner, _ = finance
    role = Role.objects.get(company=company, is_system=True, name='Administrateur')
    RolePermission.objects.filter(role=role).exclude(permission_id__in=['company.view', 'contacts.view', 'inventory.delivery.view']).delete()
    data = client.get(endpoint(company, partner) + 'activity/', {'profile': 'customer'}).json()
    assert data['available_sections'] == [] and 'balances' not in data
    assert client.get(endpoint(company, partner) + 'activity/', {'profile': 'customer', 'section': 'deliveries'}).status_code == 403
    assert post(client, f'companies/{company.pk}/reference/partners/{partner.pk}/profiles/', {'profile': 'supplier'}).status_code == 403


def test_contacts_module_suspension_and_missing_profile_are_respected(finance):
    client, _, company, _, _, partner, _ = finance
    partner.is_customer = False; partner.save()
    assert client.get(endpoint(company, partner) + 'activity/', {'profile': 'customer'}).status_code == 404
    CompanyModule.objects.filter(company=company, module__code='contacts').update(enabled=False)
    assert client.get(endpoint(company, partner) + 'activity/', {'profile': 'supplier'}).status_code == 403
    assert post(client, f'companies/{company.pk}/reference/partners/{partner.pk}/profiles/', {'profile': 'customer'}).status_code == 403


@pytest.mark.django_db(transaction=True)
def test_concurrent_profile_addition_does_not_duplicate_partner_or_audit(finance):
    _, user, company, _, _, partner, _ = finance
    partner.is_supplier = False; partner.save()
    barrier = Barrier(2)
    def run(_):
        close_old_connections()
        try:
            client = Client(enforce_csrf_checks=True); client.force_login(User.objects.get(pk=user.pk))
            barrier.wait(timeout=20)
            return post(client, f'companies/{company.pk}/reference/partners/{partner.pk}/profiles/', {'profile': 'supplier'}).status_code
        finally: close_old_connections()
    with ThreadPoolExecutor(max_workers=2) as executor:
        assert list(executor.map(run, range(2))) == [200, 200]
    assert AuditLog.objects.filter(company=company, entity_id=partner.pk, action='partners.updated').count() == 1
