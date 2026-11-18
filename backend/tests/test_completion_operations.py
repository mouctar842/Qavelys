import io
import json
import uuid
import zipfile
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import Mock
import pytest
from django.core.management import call_command, CommandError
from django.db import DatabaseError, connections
from django.test import Client
from rest_framework.exceptions import APIException
from core import health, recovery
from core.models import AuditLog, CompanyModule, RolePermission
from core.orders import order_action
from sales.models import SalesOrder
from sales.tests.test_orders import setup, create, payload, action, post
from invoicing.tests.test_invoices import finance, save, validate as validate_invoice, credit_body
from invoicing.tests.test_payments_pdf import payment, pay_action, batch
from inventory.tests.test_fulfillment import document, validate as fulfill, detail
from tests.test_branding_platform import user, company, client_for, upload, image_file

pytestmark = pytest.mark.django_db


def close(client, tenant, order, domain='sales', verb='complete', cycle=0, **extra):
    return post(client, f'companies/{tenant.pk}/{domain}/orders/{order["id"]}/{verb}/', {'version': order['version'], 'closure_version': cycle, **extra})


def service_sale(finance):
    client, actor, tenant, other, product, partner, location = finance
    product.type = 'service'; product.save()
    order = create(client, tenant, payload(product, partner, location))
    assert action(client, tenant, order, 'confirm').status_code == 200
    return order


def execute(client, tenant, order, location, kind='deliveries', quantity='3'):
    obj, _ = document(client, tenant, order, location, quantity, kind)
    assert fulfill(client, tenant, obj, kind).status_code == 200
    return obj


def bill(client, tenant, order):
    invoice = save(client, tenant, {'request_key': str(uuid.uuid4()), 'partner_id': order['partner_id'], 'sales_order_id': order['id'], 'order_version': order['version'], 'issue_date': '2026-11-17', 'due_date': '2026-12-17', 'lines': [{'sales_order_line_id': order['lines'][0]['id'], 'quantity': '3'}]})
    assert validate_invoice(client, tenant, invoice).status_code == 200
    return invoice


def settle(client, tenant, partner, invoice):
    pay, _ = payment(client, tenant, partner, invoice['total_amount'])
    assert pay_action(client, tenant, pay, 'allocate', batch((invoice, invoice['total_amount']))).status_code == 200
    return pay


def test_sale_requires_delivery_billing_payment_and_replay_cycle(finance):
    client, actor, tenant, _, _, partner, location = finance
    order = service_sale(finance)
    assert close(client, tenant, order).status_code == 400
    execute(client, tenant, order, location)
    assert close(client, tenant, order).status_code == 400
    invoice = bill(client, tenant, order)
    partial, _ = payment(client, tenant, partner, '0.20')
    assert pay_action(client, tenant, partial, 'allocate', batch((invoice, '0.20'))).status_code == 200
    assert close(client, tenant, order).status_code == 400
    remainder = str(__import__('decimal').Decimal(invoice['total_amount']) - __import__('decimal').Decimal('0.20'))
    pay, _ = payment(client, tenant, partner, remainder)
    assert pay_action(client, tenant, pay, 'allocate', batch((invoice, remainder))).status_code == 200
    for _ in range(2): assert close(client, tenant, order).status_code == 200
    saved = SalesOrder.objects.get(pk=order['id'])
    assert saved.status == 'completed' and saved.completed_at and saved.completed_by == actor and saved.closure_version == 1
    assert AuditLog.objects.filter(company=tenant, action='sales.order_complete').count() == 1
    assert action(client, tenant, order, 'cancel').status_code == 400
    assert close(client, tenant, order, verb='resume', cycle=1, reason='court').status_code == 400
    for _ in range(2): assert close(client, tenant, order, verb='resume', cycle=1, reason='Contrôle complémentaire').status_code == 200
    saved.refresh_from_db(); assert saved.status == 'confirmed' and saved.completed_at is None and saved.closure_version == 2
    assert close(client, tenant, order, cycle=0).status_code == 409
    assert close(client, tenant, order, cycle=2).status_code == 200
    assert close(client, tenant, order, verb='resume', cycle=1, reason='Ancienne requête retardée').status_code == 409


def test_purchase_receipt_drafts_permissions_modules_and_foreign_ids(setup):
    client, _, tenant, other, product, partner, location = setup
    order = create(client, tenant, payload(product, partner, location), 'purchases')
    assert close(client, tenant, order, 'purchases').status_code == 400
    assert action(client, tenant, order, 'confirm', 'purchases').status_code == 200
    draft, _ = document(client, tenant, order, location, '1', 'receipts')
    execute(client, tenant, order, location, 'receipts')
    assert close(client, tenant, order, 'purchases').status_code == 400
    assert post(client, f'companies/{tenant.id}/inventory/receipts/{draft["id"]}/cancel/', {}).status_code == 200
    assert close(client, other, order, 'purchases').status_code == 404
    assert client.post(f'/api/v1/companies/{tenant.id}/purchases/orders/{order["id"]}/complete/', {}).status_code == 403
    assert post(client, f'companies/{tenant.id}/purchases/orders/{order["id"]}/complete/', {'version': 1}).status_code == 400
    permission = RolePermission.objects.get(role__company=tenant, role__is_system=True, permission_id='purchases.order.complete')
    permission.delete()
    assert close(client, tenant, order, 'purchases').status_code == 403
    RolePermission.objects.create(role=permission.role, permission_id='purchases.order.complete')
    CompanyModule.objects.filter(company=tenant, module__code='inventory').update(enabled=False)
    assert close(client, tenant, order, 'purchases').status_code == 403
    CompanyModule.objects.filter(company=tenant, module__code='inventory').update(enabled=True)
    assert close(client, tenant, order, 'purchases').status_code == 200


def test_credit_corrections_remain_possible_and_current_balances_update(finance):
    client, _, tenant, _, _, partner, location = finance
    order = service_sale(finance); execute(client, tenant, order, location)
    invoice = bill(client, tenant, order); settle(client, tenant, partner, invoice)
    credit = save(client, tenant, credit_body(invoice, '1'), 'credit-notes')
    assert close(client, tenant, order).status_code == 400  # Avoir brouillon encore à traiter.
    assert post(client, f'companies/{tenant.id}/invoicing/credit-notes/{credit["id"]}/cancel/', {}).status_code == 200
    assert close(client, tenant, order).status_code == 200
    credit = save(client, tenant, credit_body(invoice, '1'), 'credit-notes')
    assert validate_invoice(client, tenant, credit, 'credit-notes').status_code == 200
    state = detail(client, tenant, order)['completion']
    assert not state['eligible'] and any('crédit' in reason for reason in state['reasons'])
    assert SalesOrder.objects.get(pk=order['id']).status == 'completed'
    assert close(client, tenant, order, verb='resume', cycle=1, reason='Correction après avoir').status_code == 200
    assert close(client, tenant, order, cycle=2).status_code == 400
    RolePermission.objects.filter(role__company=tenant, permission_id='invoicing.payment.view').delete()
    assert detail(client, tenant, order)['completion'] is None
    assert close(client, tenant, order, cycle=2).status_code == 403


@pytest.mark.django_db(transaction=True)
def test_concurrent_completion_has_one_audit(finance):
    client, actor, tenant, _, _, partner, location = finance
    order = service_sale(finance); execute(client, tenant, order, location)
    invoice = bill(client, tenant, order); settle(client, tenant, partner, invoice)
    barrier = Barrier(2)
    def run(_):
        connections.close_all(); barrier.wait(timeout=10)
        try: return order_action(actor, tenant.id, 'sales', order['id'], 'complete', 1, closure_version=0).status
        finally: connections.close_all()
    with ThreadPoolExecutor(max_workers=2) as executor: assert list(executor.map(run, range(2))) == ['completed', 'completed']
    assert AuditLog.objects.filter(company=tenant, action='sales.order_complete').count() == 1


@pytest.mark.django_db(transaction=True)
def test_completion_serializes_with_payment_reversal(finance):
    from core.completion import completion_state
    from invoicing.models import PaymentAllocation
    from invoicing.payments import reverse_allocation
    client, actor, tenant, _, _, partner, location = finance
    order = service_sale(finance); execute(client, tenant, order, location)
    invoice = bill(client, tenant, order); pay = settle(client, tenant, partner, invoice)
    allocation = PaymentAllocation.objects.get(payment_id=pay['id'])
    barrier = Barrier(2)
    def run(kind):
        connections.close_all(); barrier.wait(timeout=10)
        try:
            if kind == 'reverse':
                reverse_allocation(actor, tenant.id, allocation.id, {'reason': 'Correction concurrente'})
                return 'reversed'
            try: return order_action(actor, tenant.id, 'sales', order['id'], 'complete', 1, closure_version=0).status
            except APIException as exc:
                assert exc.status_code == 400
                return 'refused'
        finally: connections.close_all()
    with ThreadPoolExecutor(max_workers=2) as executor: result = list(executor.map(run, ['close', 'reverse']))
    assert result[1] == 'reversed' and result[0] in ('completed', 'refused')
    saved = SalesOrder.objects.get(pk=order['id'])
    assert saved.status == ('completed' if result[0] == 'completed' else 'confirmed')
    state = completion_state(actor, saved, 'sales')
    assert not state['eligible'] and any('réglées' in reason for reason in state['reasons'])


def test_health_probes_and_failures_are_minimal(monkeypatch, django_assert_num_queries):
    client = Client()
    with django_assert_num_queries(0): assert client.get('/api/v1/health/live/').json() == {'status': 'ok'}
    assert client.post('/api/v1/health/live/').status_code == 405
    response = client.get('/api/v1/health/ready/'); assert response.status_code == 200 and response['Cache-Control'] == 'no-store'
    executor = Mock(); executor.migration_plan.return_value = [object()]
    monkeypatch.setattr(health, 'MigrationExecutor', lambda conn: executor)
    assert client.get('/api/v1/health/ready/').status_code == 503
    monkeypatch.setattr(health.connection, 'cursor', Mock(side_effect=DatabaseError('PRIVATE-CONNECTION-DETAIL')))
    response = client.get('/api/v1/health/ready/')
    assert response.status_code == 503 and response.json() == {'status': 'unavailable'}
    assert 'PRIVATE' not in response.content.decode()
    from core.management.commands import healthcheck
    monkeypatch.setattr(healthcheck, 'ready', lambda: False)
    with pytest.raises(CommandError): call_command('healthcheck')


def bundle(tmp_path, monkeypatch, name='safe.png'):
    monkeypatch.setattr(recovery, 'ROOT', tmp_path)
    folder = tmp_path / '.local' / 'backups' / 'fixture'; folder.mkdir(parents=True)
    (folder / 'database.dump').write_bytes(b'unit-test-dump-not-executed')
    with zipfile.ZipFile(folder / 'media.zip', 'w') as archive: archive.writestr(name, b'qa')
    expected = {'size': 2, 'sha256': __import__('hashlib').sha256(b'qa').hexdigest()}
    manifest = {'format': 1, 'database': recovery.digest_file(folder / 'database.dump'), 'media_archive': recovery.digest_file(folder / 'media.zip'), 'media_files': {name: expected}, 'referenced_media': {}, 'facts': {'tables': {}, 'sequences': {}}, 'locale': {'provider': 'c'}}
    (folder / 'manifest.json').write_text(json.dumps(manifest))
    return folder


@pytest.mark.parametrize('name', ['../escape.png', '/absolute.png', 'C:/private.png', 'folder\\escape.png', 'NUL.png', 'folder/../escape.png'])
def test_restore_rejects_unsafe_media_before_connecting(tmp_path, monkeypatch, name):
    folder = bundle(tmp_path, monkeypatch, name)
    monkeypatch.setattr(recovery.psycopg, 'connect', Mock(side_effect=AssertionError('No database connection expected')))
    with pytest.raises(CommandError): recovery.restore(folder)


def test_restore_rejects_corruption_and_user_database(tmp_path, monkeypatch):
    folder = bundle(tmp_path, monkeypatch)
    assert recovery.validate_bundle(folder)['format'] == 1
    monkeypatch.setattr(recovery.psycopg, 'connect', Mock(side_effect=AssertionError('No database connection expected')))
    with pytest.raises(CommandError): recovery.restore(folder, recovery.config()['dbname'])
    (folder / 'database.dump').write_bytes(b'tampered')
    with pytest.raises(CommandError): recovery.restore(folder)


@pytest.mark.django_db(transaction=True)
def test_real_backup_restore_private_media_tables_sequences_and_no_overwrite(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path / 'source-media'
    owner = user('qa-recovery@example.invalid'); tenant = company(owner, 'QA sauvegarde')
    assert upload(client_for(owner), tenant.id, image_file()).status_code == 201
    source = recovery.config()['dbname']
    folder = recovery.backup(); result = recovery.restore(folder)
    assert result['verified'] and result['database'] != source and result['media_files'] == 1
    with pytest.raises((CommandError, FileExistsError)): recovery.restore(folder, result['database'])
    with pytest.raises(CommandError): recovery.create_target(recovery.config(), source, recovery.validate_bundle(folder)['locale'])
    assert recovery.config()['dbname'] == source
