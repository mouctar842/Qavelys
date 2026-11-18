import uuid
from datetime import timedelta
from decimal import Decimal
from concurrent.futures import ThreadPoolExecutor
import pytest
from django.db import IntegrityError, transaction, close_old_connections, connection
from django.utils import timezone
from django.test import Client
from django.test.utils import CaptureQueriesContext
from core.models import Module, CompanyModule, Membership, User, Role, MembershipRole, RolePermission, Notification
from core.notifications import sync
from crm.models import Lead, CRMActivity
from invoicing.models import Invoice, CreditNote, PaymentAllocation
from invoicing.payments import invoice_balance
from invoicing.queries import invoice_balances
from invoicing.tests.test_invoices import finance, save, invoice_body, credit_body, validate as validate_invoice
from invoicing.tests.test_payments_pdf import payment, pay_action, batch
from sales.tests.test_orders import setup, post, payload, create, action, rule
from inventory.models import StockLocation, StockBalance

pytestmark = pytest.mark.django_db


@pytest.fixture
def workspace(finance):
    client, user, company, other, product, partner, location = finance
    module, _ = Module.objects.get_or_create(code='dashboard', defaults={'name': 'Dashboard', 'status': 'available'})
    for current in [company, other]: CompanyModule.objects.get_or_create(company=current, module=module, defaults={'enabled': True})
    return finance


def dashboard(client, company, **params): return client.get(f'/api/v1/companies/{company.pk}/dashboard/', params)


def sync_api(client, company): return post(client, f'companies/{company.pk}/notifications/sync/', {})


def inbox(client, company): return client.get(f'/api/v1/companies/{company.pk}/notifications/').json()


def test_actual_flows_currency_and_no_join_multiplication(workspace):
    client, _, company, other, _, partner, _ = workspace
    invoice = save(client, company, invoice_body(partner, lines=[{'description': 'Réel', 'quantity': '10', 'unit_price': '10'}])); validate_invoice(client, company, invoice)
    for _ in range(2):
        credit = save(client, company, credit_body(invoice, '1'), 'credit-notes'); validate_invoice(client, company, credit, 'credit-notes')
        pay, _ = payment(client, company, partner, '15'); assert pay_action(client, company, pay, 'allocate', batch((invoice, '15'))).status_code == 200
    company.currency_code = 'GNF'; company.save()
    gnf = save(client, company, invoice_body(partner, lines=[{'description': 'Autre devise', 'quantity': '1', 'unit_price': '1000'}])); validate_invoice(client, company, gnf)
    assert invoice_balance(Invoice.objects.get(pk=invoice['id']))['amount_due'] == 50
    annotated = invoice_balances(Invoice.objects.filter(pk=invoice['id'])).get()
    assert annotated.outstanding == 50 and annotated.allocated_total == 30 and annotated.credited_total == 20
    result = dashboard(client, company, start='2026-11-01', end='2026-11-30'); assert result.status_code == 200
    section = result.json()['sections']['invoicing']
    totals = {row['currency_code']: row for row in section['totals']}
    assert Decimal(totals['EUR']['net']) == 80 and Decimal(totals['GNF']['net']) == 1000
    assert {row['currency_code']: Decimal(row['amount']) for row in section['amount_due']} == {'EUR': Decimal(50), 'GNF': Decimal(1000)}
    assert section['invoice_count'] == 2
    assert dashboard(client, other, start='2026-11-01', end='2026-11-30').json()['sections']['invoicing']['invoice_count'] == 0


def test_periods_credit_on_old_invoice_and_live_snapshots(workspace):
    client, _, company, _, _, partner, _ = workspace
    invoice = save(client, company, invoice_body(partner, issue_date='2026-10-20', due_date='2026-10-25', lines=[{'description': 'Octobre', 'quantity': '1', 'unit_price': '100'}])); validate_invoice(client, company, invoice)
    credit = save(client, company, credit_body(invoice), 'credit-notes'); validate_invoice(client, company, credit, 'credit-notes')
    result = dashboard(client, company, start='2026-11-01', end='2026-11-30').json()['sections']['invoicing']
    assert result['invoice_count'] == 0 and Decimal(result['totals'][0]['net']) == -100
    assert result['unpaid_count'] == 0
    for params in [{'start': '2026-11-20', 'end': '2026-11-01'}, {'start': '2024-01-01', 'end': '2026-11-01'}, {'start': 'invalide'}]:
        assert dashboard(client, company, **params).status_code == 400


def test_permissions_disabled_modules_and_bounded_queries(workspace):
    client, _, company, _, _, partner, _ = workspace
    for _ in range(3):
        obj = save(client, company, invoice_body(partner)); validate_invoice(client, company, obj)
    with CaptureQueriesContext(connection) as queries: result = dashboard(client, company)
    assert result.status_code == 200 and len(queries) < 55
    RolePermission.objects.filter(role__company=company, permission_id__in=['invoicing.invoice.view', 'invoicing.payment.view']).delete()
    sections = dashboard(client, company).json()['sections']
    assert 'invoicing' not in sections and 'payments' not in sections
    CompanyModule.objects.filter(company=company, module__code='sales').update(enabled=False)
    assert 'sales' not in dashboard(client, company).json()['sections']
    CompanyModule.objects.filter(company=company, module__code='dashboard').update(enabled=False)
    assert dashboard(client, company).status_code == 403


def test_stock_waiting_and_crm_are_real_and_resolve(workspace):
    client, user, company, _, product, partner, location = workspace
    StockBalance.objects.create(company=company, product=product, location=location, quantity=2)
    order = create(client, company, payload(product, partner, location, quantity='5')); action(client, company, order, 'confirm')
    member = Membership.objects.get(company=company, user=user)
    lead = Lead.objects.create(company=company, owner=member, title='Prospect réel')
    activity = CRMActivity.objects.create(company=company, lead=lead, assigned_to=member, type='task', due_at=timezone.now() - timedelta(hours=1), description='Rappeler')
    result = dashboard(client, company).json()['sections']
    assert result['inventory']['waiting_lines'] == 1 and Decimal(result['inventory']['orders_waiting'][0]['waiting_quantity']) == 3
    assert result['inventory']['unavailable_products'] == 1 and result['crm']['late_activities'] == 1
    activity.status = 'done'; activity.save()
    assert dashboard(client, company).json()['sections']['crm']['late_activities'] == 0


def test_notifications_personal_idempotent_read_and_postponed_activity(workspace):
    client, user, company, other, _, _, _ = workspace
    member = Membership.objects.get(company=company, user=user)
    lead = Lead.objects.create(company=company, owner=member, title='À relancer')
    activity = CRMActivity.objects.create(company=company, lead=lead, assigned_to=member, type='task', due_at=timezone.now() - timedelta(days=1), description='Appeler le client')
    assert sync_api(client, company).status_code == 200 and sync_api(client, company).json()['created'] == 0
    notification = Notification.objects.get()
    assert inbox(client, company)['unread_count'] == 1
    url = f'companies/{company.pk}/notifications/{notification.pk}/read/'
    assert post(client, url, {'read': True}).status_code == 200 and post(client, url, {'read': True}).status_code == 200
    assert inbox(client, company)['unread_count'] == 0
    assert post(client, url, {'read': False}).status_code == 200
    assert post(client, f'companies/{other.pk}/notifications/{notification.pk}/read/', {'read': True}).status_code == 404
    foreign = Membership.objects.get(company=other, user=user)
    with pytest.raises(IntegrityError), transaction.atomic(): Notification.objects.filter(pk=notification.pk).update(recipient=foreign)
    activity.due_at = timezone.now() + timedelta(days=1); activity.save()
    assert inbox(client, company)['count'] == 0 and Notification.objects.count() == 1
    activity.due_at = timezone.now() - timedelta(minutes=1); activity.save()
    assert sync_api(client, company).json()['created'] == 1
    assert inbox(client, company)['count'] == 1 and Notification.objects.count() == 2
    assert post(client, f'companies/{company.pk}/notifications/read-all/', {}).json()['marked_read'] == 1


def test_notification_rights_approvals_and_financial_resolution(workspace):
    client, _, company, _, product, partner, location = workspace
    rule(client, company, minimum='0')
    order = create(client, company, payload(product, partner, location)); action(client, company, order, 'submit')
    assert sync_api(client, company).status_code == 200
    pending = Notification.objects.get(type='approval_request')
    response = post(client, f'companies/{company.pk}/approvals/requests/{pending.approval_request_id}/decide/', {'decision': 'approved'}); assert response.status_code == 200
    assert sync_api(client, company).status_code == 200
    assert [row['type'] for row in inbox(client, company)['results']] == ['approval_decision']
    obj = save(client, company, invoice_body(partner, issue_date='2026-10-01', due_date='2026-10-05')); validate_invoice(client, company, obj)
    sync_api(client, company)
    assert 'invoice_overdue' in [row['type'] for row in inbox(client, company)['results']]
    credit = save(client, company, credit_body(obj, '3'), 'credit-notes'); validate_invoice(client, company, credit, 'credit-notes')
    assert 'invoice_overdue' not in [row['type'] for row in inbox(client, company)['results']]
    RolePermission.objects.filter(role__company=company, permission_id='sales.order.view').delete()
    assert inbox(client, company)['count'] == 0


@pytest.mark.django_db(transaction=True)
def test_concurrent_sync_does_not_duplicate_and_other_recipient_cannot_read(workspace):
    client, user, company, _, _, partner, _ = workspace
    obj = save(client, company, invoice_body(partner, issue_date='2026-10-01', due_date='2026-10-05')); validate_invoice(client, company, obj)
    def work(_):
        close_old_connections()
        try: return sync(user, company.pk)
        finally: close_old_connections()
    with ThreadPoolExecutor(max_workers=2) as pool: assert sorted(pool.map(work, range(2))) == [0, 1]
    notification = Notification.objects.get()
    other_user = User.objects.create_user('notify-other@example.com', 'Long-password!2026', email_verified=True)
    other_member = Membership.objects.create(company=company, user=other_user)
    MembershipRole.objects.create(company=company, membership=other_member, role=Role.objects.get(company=company, is_system=True))
    other_client = Client(enforce_csrf_checks=True); other_client.force_login(other_user)
    assert post(other_client, f'companies/{company.pk}/notifications/{notification.pk}/read/', {'read': True}).status_code == 404
    assert Notification.objects.count() == 1
