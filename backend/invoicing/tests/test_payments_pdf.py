import uuid
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import pytest
from pypdf import PdfReader
from django.conf import settings
from django.db import IntegrityError, transaction, close_old_connections
from core.models import CompanyModule, RolePermission
from reference.models import Partner
from invoicing.models import Payment, PaymentAllocation, Invoice
from invoicing.payments import allocate
from invoicing.tests.test_invoices import finance, save, invoice_body, credit_body, validate as validate_invoice
from sales.tests.test_orders import post, setup

pytestmark = pytest.mark.django_db


def make_invoice(client, company, partner, amount='100'):
    obj = save(client, company, invoice_body(partner, lines=[{'description': 'Prestation réelle', 'quantity': '1', 'unit_price': amount}]))
    assert validate_invoice(client, company, obj).status_code == 200
    return obj


def payment(client, company, partner, amount='100', validated=True):
    body = {'request_key': str(uuid.uuid4()), 'partner_id': str(partner.pk), 'amount': amount, 'method': 'bank_transfer', 'payment_date': '2026-11-17', 'external_reference': 'BANQUE-123'}
    response = post(client, f'companies/{company.pk}/invoicing/payments/', body)
    assert response.status_code == 201, response.content
    obj = response.json()
    if validated: assert pay_action(client, company, obj, 'validate').status_code == 200
    return obj, body


def pay_action(client, company, obj, action, data=None):
    return post(client, f'companies/{company.pk}/invoicing/payments/{obj["id"]}/{action}/', data or {})


def batch(*rows): return {'request_key': str(uuid.uuid4()), 'allocations': [{'invoice_id': row['id'], 'amount': amount} for row, amount in rows]}


def invoice_detail(client, company, obj): return client.get(f'/api/v1/companies/{company.pk}/invoicing/invoices/{obj["id"]}/').json()


def test_partial_multiple_payments_and_batch_replay_and_reversal(finance):
    client, _, company, _, _, partner, _ = finance
    first, second = [make_invoice(client, company, partner) for _ in range(2)]
    one, body = payment(client, company, partner, '120')
    assert post(client, f'companies/{company.pk}/invoicing/payments/', body).status_code == 200
    assert post(client, f'companies/{company.pk}/invoicing/payments/', {**body, 'amount': '130'}).status_code == 400
    payload = batch((first, '60'), (second, '40'))
    result = pay_action(client, company, one, 'allocate', payload)
    assert result.status_code == 200 and Decimal(result.json()['available_amount']) == 20
    assert pay_action(client, company, one, 'allocate', payload).status_code == 200 and PaymentAllocation.objects.count() == 2
    assert invoice_detail(client, company, first)['payment_status'] == 'partial'
    two, _ = payment(client, company, partner, '80')
    assert pay_action(client, company, two, 'allocate', batch((first, '40'), (second, '40'))).status_code == 200
    assert pay_action(client, company, one, 'allocate', batch((second, '20'))).status_code == 200
    assert invoice_detail(client, company, second)['payment_status'] == 'paid'
    allocation = PaymentAllocation.objects.get(payment_id=one['id'], invoice_id=first['id'])
    url = f'companies/{company.pk}/invoicing/payments/allocations/{allocation.pk}/reverse/'
    assert post(client, url, {'reason': 'Réaffectation'}).status_code == 200
    assert post(client, url, {'reason': 'Réaffectation'}).status_code == 200
    assert Decimal(invoice_detail(client, company, first)['amount_due']) == 60
    assert pay_action(client, company, one, 'allocate', payload).status_code == 200  # ne réactive pas l’historique extourné
    allocation.refresh_from_db(); assert allocation.status == 'reversed'
    assert pay_action(client, company, one, 'allocate', batch((first, '60'))).status_code == 200
    assert invoice_detail(client, company, first)['payment_status'] == 'paid'


def test_excess_allocation_atomicity_credit_after_payment_and_cancel(finance):
    client, _, company, _, _, partner, _ = finance
    first = make_invoice(client, company, partner)
    second = make_invoice(client, company, partner, '10')
    pay, _ = payment(client, company, partner, '120')
    assert pay_action(client, company, pay, 'allocate', batch((first, '90'), (second, '20'))).status_code == 400
    assert not PaymentAllocation.objects.exists()
    result = pay_action(client, company, pay, 'allocate', batch((first, '100'))); assert result.status_code == 200
    credit = save(client, company, credit_body(first, '1'), 'credit-notes'); assert validate_invoice(client, company, credit, 'credit-notes').status_code == 200
    data = invoice_detail(client, company, first); assert Decimal(data['credit_balance']) == 100 and Decimal(data['amount_due']) == 0
    assert pay_action(client, company, pay, 'cancel', {'reason': 'Erreur'}).status_code == 400
    row = PaymentAllocation.objects.get()
    assert post(client, f'companies/{company.pk}/invoicing/payments/allocations/{row.pk}/reverse/', {'reason': 'Libération après avoir'}).status_code == 200
    assert Decimal(invoice_detail(client, company, first)['credit_balance']) == 0
    assert pay_action(client, company, pay, 'cancel').status_code == 400
    assert pay_action(client, company, pay, 'cancel', {'reason': 'Erreur de saisie'}).status_code == 200
    assert pay_action(client, company, pay, 'cancel').status_code == 200
    assert Payment.objects.get().cancellation_reason == 'Erreur de saisie'
    assert pay_action(client, company, pay, 'validate').status_code == 400


@pytest.mark.parametrize('currency,amount', [('EUR', '1.001'), ('GNF', '1.2'), ('XOF', '0.01')])
def test_currency_precision_and_float_rejection(finance, currency, amount):
    client, _, company, _, _, partner, _ = finance
    company.currency_code = currency; company.save()
    body = {'request_key': str(uuid.uuid4()), 'partner_id': str(partner.pk), 'amount': amount, 'method': 'cash', 'payment_date': '2026-11-17'}
    assert post(client, f'companies/{company.pk}/invoicing/payments/', body).status_code == 400
    body['amount'] = 1.5
    assert post(client, f'companies/{company.pk}/invoicing/payments/', body).status_code == 400
    body['amount'] = '1'
    result = post(client, f'companies/{company.pk}/invoicing/payments/', body)
    assert result.status_code == 201 and result.json()['currency_code'] == currency


def test_due_date_currency_and_customer_are_independent_guards(finance, monkeypatch):
    from datetime import date
    from django.utils import timezone
    client, _, company, _, _, partner, _ = finance
    second_partner = Partner.objects.create(company=company, name='Second client')
    foreign_customer_invoice = make_invoice(client, company, second_partner)
    invoice = make_invoice(client, company, partner)
    pay, _ = payment(client, company, partner)
    assert pay_action(client, company, pay, 'allocate', batch((foreign_customer_invoice, '1'))).status_code == 400
    Invoice.objects.filter(pk=invoice['id']).update(currency_code='GNF')
    assert pay_action(client, company, pay, 'allocate', batch((invoice, '1'))).status_code == 400
    Invoice.objects.filter(pk=invoice['id']).update(currency_code='EUR', due_date=date(2026, 11, 17))
    monkeypatch.setattr(timezone, 'localdate', lambda *args, **kwargs: date(2026, 11, 18))
    assert invoice_detail(client, company, invoice)['payment_status'] == 'overdue'
    assert pay_action(client, company, pay, 'allocate', batch((invoice, '100'))).status_code == 200
    assert invoice_detail(client, company, invoice)['payment_status'] == 'paid'


def test_foreign_relations_permissions_csrf_and_module(finance):
    client, _, company, other, _, partner, _ = finance
    foreign_partner = Partner.objects.create(company=other, name='Étranger')
    foreign_invoice = make_invoice(client, other, foreign_partner)
    pay, _ = payment(client, company, partner)
    assert pay_action(client, company, pay, 'allocate', batch((foreign_invoice, '1'))).status_code == 400
    assert client.get(f'/api/v1/companies/{other.pk}/invoicing/payments/{pay["id"]}/').status_code == 404
    with pytest.raises(IntegrityError), transaction.atomic(): Payment.objects.filter(pk=pay['id']).update(partner=foreign_partner)
    local = make_invoice(client, company, partner)
    assert pay_action(client, company, pay, 'allocate', batch((local, '50'))).status_code == 200
    row = PaymentAllocation.objects.get()
    with pytest.raises(IntegrityError), transaction.atomic(): PaymentAllocation.objects.filter(pk=row.pk).update(invoice_id=foreign_invoice['id'])
    assert client.post(f'/api/v1/companies/{company.pk}/invoicing/payments/{pay["id"]}/allocate/', data='{}', content_type='application/json').status_code == 403
    RolePermission.objects.filter(role__company=company, permission_id='invoicing.invoice.view').delete()
    response = client.get(f'/api/v1/companies/{company.pk}/invoicing/payments/{pay["id"]}/').json()
    assert response['allocations'] == [] and Decimal(response['allocated_amount']) == 50
    assert pay_action(client, company, pay, 'allocate', batch((local, '1'))).status_code == 403
    CompanyModule.objects.filter(company=company, module__code='invoicing').update(enabled=False)
    assert client.get(f'/api/v1/companies/{company.pk}/invoicing/payments/').status_code == 403


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize('same_payment', [True, False])
def test_concurrent_allocations_cannot_overdraw_payment_or_invoice(finance, same_payment):
    client, user, company, _, _, partner, _ = finance
    invoices = [make_invoice(client, company, partner) for _ in range(2)]
    pay1, _ = payment(client, company, partner)
    pay2 = pay1 if same_payment else payment(client, company, partner)[0]
    jobs = [(pay1, invoices[0]), (pay2, invoices[1] if same_payment else invoices[0])]
    def work(job):
        from rest_framework.exceptions import ValidationError
        close_old_connections()
        try: allocate(user, company.pk, job[0]['id'], batch((job[1], '80'))); return 'ok'
        except ValidationError: return 'rejected'
        finally: close_old_connections()
    with ThreadPoolExecutor(max_workers=2) as pool: assert sorted(pool.map(work, jobs)) == ['ok', 'rejected']
    assert PaymentAllocation.objects.count() == 1 and PaymentAllocation.objects.get().amount == 80


def test_pdf_content_headers_snapshots_and_tenant_access(finance):
    client, _, company, other, _, partner, _ = finance
    obj = make_invoice(client, company, partner, '123.45')
    url = f'/api/v1/companies/{company.pk}/invoicing/invoices/{obj["id"]}/pdf/'
    partner.name = 'Nom changé après validation'; partner.save()
    response = client.get(url); assert response.status_code == 200
    assert response['Content-Type'] == 'application/pdf' and 'no-store' in response['Cache-Control']
    reader = PdfReader(BytesIO(response.content)); content = '\n'.join(page.extract_text() for page in reader.pages)
    assert '123.45 EUR' in content and 'Client fournisseur' in content and 'Nom changé' not in content
    output = Path(settings.BASE_DIR).parent / '.local/pdf-qa'; output.mkdir(parents=True, exist_ok=True)
    (output / 'invoice-short.pdf').write_bytes(response.content)
    credit = save(client, company, credit_body(obj), 'credit-notes'); validate_invoice(client, company, credit, 'credit-notes')
    response = client.get(f'/api/v1/companies/{company.pk}/invoicing/credit-notes/{credit["id"]}/pdf/'); assert response.status_code == 200
    (output / 'credit-short.pdf').write_bytes(response.content)
    assert 'AVOIR CLIENT' in PdfReader(BytesIO(response.content)).pages[0].extract_text()
    assert client.get(f'/api/v1/companies/{other.pk}/invoicing/invoices/{obj["id"]}/pdf/').status_code == 404
    RolePermission.objects.filter(role__company=company, permission_id='invoicing.document.export').delete()
    assert client.get(url).status_code == 403


def test_pdf_multipage_long_text_escaping_and_draft_refusal(finance):
    client, _, company, _, _, partner, _ = finance
    description = 'Désignation détaillée <b>texte littéral</b> & précision. ' * 15
    obj = save(client, company, invoice_body(partner, lines=[{'description': f'Ligne {i + 1} - {description}', 'quantity': '1', 'unit_price': '0.335', 'tax_rate': '20'} for i in range(40)]))
    url = f'/api/v1/companies/{company.pk}/invoicing/invoices/{obj["id"]}/pdf/'
    assert client.get(url).status_code == 400
    validate_invoice(client, company, obj)
    response = client.get(url); assert response.status_code == 200
    reader = PdfReader(BytesIO(response.content)); assert len(reader.pages) > 1
    text = '\n'.join(page.extract_text() for page in reader.pages)
    assert 'Ligne 40' in text and '<b>texte littéral</b>' in text and '16.08 EUR' in text
    output = Path(settings.BASE_DIR).parent / '.local/pdf-qa'; output.mkdir(parents=True, exist_ok=True)
    (output / 'invoice-long.pdf').write_bytes(response.content)
