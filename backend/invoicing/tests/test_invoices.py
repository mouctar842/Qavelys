import uuid
from decimal import Decimal
from concurrent.futures import ThreadPoolExecutor
import pytest
from django.db import IntegrityError, transaction, close_old_connections
from core.models import CompanyModule, Module, RolePermission
from sales.tests.test_orders import setup, payload, create, action, post
from invoicing.models import Invoice, InvoiceLine, CreditNote, CreditNoteLine
from invoicing.services import document_action
from inventory.models import StockMovement, StockBalance

pytestmark = pytest.mark.django_db


@pytest.fixture
def finance(setup):
    client, user, company, other, product, partner, location = setup
    module, _ = Module.objects.get_or_create(code='invoicing', defaults={'name': 'Facturation', 'status': 'available'})
    for current in [company, other]: CompanyModule.objects.get_or_create(company=current, module=module, defaults={'enabled': True})
    return setup


def invoice_body(partner, **extra):
    return {'request_key': str(uuid.uuid4()), 'partner_id': str(partner.pk), 'issue_date': '2026-11-17', 'due_date': '2026-12-17', 'lines': [{'description': 'Prestation', 'quantity': '3', 'unit_price': '0.335', 'tax_rate': '20'}], **extra}


def save(client, company, body, kind='invoices'):
    response = post(client, f'companies/{company.pk}/invoicing/{kind}/', body)
    assert response.status_code == 201, response.content
    return response.json()


def validate(client, company, obj, kind='invoices'):
    return post(client, f'companies/{company.pk}/invoicing/{kind}/{obj["id"]}/validate/', {})


def credit_body(invoice, quantity='1'):
    return {'request_key': str(uuid.uuid4()), 'invoice_id': invoice['id'], 'issue_date': '2026-11-17', 'reason': 'Correction de quantité', 'lines': [{'invoice_line_id': invoice['lines'][0]['id'], 'quantity': quantity}]}


@pytest.mark.parametrize('currency,expected', [('EUR', '1.21'), ('GNF', '1'), ('XOF', '1')])
def test_direct_invoice_rounding_snapshots_and_immutability(finance, currency, expected):
    client, _, company, _, _, partner, _ = finance
    company.currency_code = currency; company.save()
    body = invoice_body(partner, lines=[{'description': 'Ligne', 'quantity': '1', 'unit_price': '0.335', 'tax_rate': '20'} for _ in range(3)])
    invoice = save(client, company, body)
    assert Decimal(invoice['total_amount']) == Decimal(expected)
    assert post(client, f'companies/{company.pk}/invoicing/invoices/', body).status_code == 200
    assert Invoice.objects.count() == 1
    assert validate(client, company, invoice).status_code == 200
    assert validate(client, company, invoice).status_code == 200
    partner.name = 'Nouveau nom'; partner.save()
    detail = client.get(f'/api/v1/companies/{company.pk}/invoicing/invoices/{invoice["id"]}/').json()
    assert detail['partner_name'] == 'Client fournisseur'
    assert detail['issuer_snapshot']['name'] == company.name
    assert post(client, f'companies/{company.pk}/invoicing/invoices/{invoice["id"]}/cancel/', {}).status_code == 400
    assert not StockBalance.objects.exists() and not StockMovement.objects.exists()


def test_multiple_order_invoices_and_credit_releases_quota(finance):
    client, _, company, _, product, partner, location = finance
    order = create(client, company, payload(product, partner, location, quantity='100')); action(client, company, order, 'confirm')
    invoices = []
    def body(quantity): return invoice_body(partner, sales_order_id=order['id'], order_version=1, lines=[{'sales_order_line_id': order['lines'][0]['id'], 'quantity': quantity, 'unit_price': '999', 'tax_rate': '0'}])
    product.sale_price = '12'; product.save()
    for quantity in ['40', '35', '25']:
        invoice = save(client, company, body(quantity)); assert Decimal(invoice['lines'][0]['unit_price']) == Decimal('.335')
        assert validate(client, company, invoice).status_code == 200
        invoices.append(invoice)
    assert post(client, f'companies/{company.pk}/invoicing/invoices/', body('1')).status_code == 400
    credit = save(client, company, credit_body(invoices[0], '10'), 'credit-notes'); assert validate(client, company, credit, 'credit-notes').status_code == 200
    replacement = save(client, company, body('10')); assert validate(client, company, replacement).status_code == 200
    assert post(client, f'companies/{company.pk}/invoicing/invoices/', body('1')).status_code == 400
    order_data = client.get(f'/api/v1/companies/{company.pk}/sales/orders/{order["id"]}/').json()
    assert order_data['invoicing_status'] == 'done' and Decimal(order_data['lines'][0]['billed_quantity']) == 100
    assert 'cancel' not in order_data['allowed_actions']
    assert action(client, company, order, 'cancel').status_code == 400


def test_credit_rounding_cumulative_full_refund_and_stale_preview(finance):
    client, _, company, _, _, partner, _ = finance
    invoice = save(client, company, invoice_body(partner)); validate(client, company, invoice)
    first = save(client, company, credit_body(invoice), 'credit-notes')
    stale = save(client, company, credit_body(invoice), 'credit-notes')
    assert validate(client, company, first, 'credit-notes').status_code == 200
    assert validate(client, company, first, 'credit-notes').status_code == 200
    assert validate(client, company, stale, 'credit-notes').status_code == 409
    for _ in range(2):
        obj = save(client, company, credit_body(invoice), 'credit-notes'); assert validate(client, company, obj, 'credit-notes').status_code == 200
    assert sum(CreditNote.objects.filter(status='validated').values_list('total_amount', flat=True)) == Decimal('1.21')
    assert post(client, f'companies/{company.pk}/invoicing/credit-notes/', credit_body(invoice)).status_code == 400
    result = client.get(f'/api/v1/companies/{company.pk}/invoicing/invoices/{invoice["id"]}/').json()
    assert Decimal(result['net_amount']) == 0 and Decimal(result['lines'][0]['creditable_quantity']) == 0


def test_cross_tenant_exact_input_permissions_and_module(finance):
    client, _, company, other, _, partner, _ = finance
    from reference.models import Partner
    foreign = Partner.objects.create(company=other, name='Étranger')
    body = invoice_body(partner); bad = invoice_body(foreign)
    assert post(client, f'companies/{company.pk}/invoicing/invoices/', bad).status_code == 400
    bad = invoice_body(partner); bad['lines'][0]['quantity'] = 1.2
    assert post(client, f'companies/{company.pk}/invoicing/invoices/', bad).status_code == 400
    invoice = save(client, company, body)
    assert client.get(f'/api/v1/companies/{other.pk}/invoicing/invoices/{invoice["id"]}/').status_code == 404
    with pytest.raises(IntegrityError), transaction.atomic(): Invoice.objects.filter(pk=invoice['id']).update(partner=foreign)
    RolePermission.objects.filter(role__company=company, permission_id='invoicing.invoice.validate').delete()
    assert validate(client, company, invoice).status_code == 403
    CompanyModule.objects.filter(company=company, module__code='invoicing').update(enabled=False)
    assert client.get(f'/api/v1/companies/{company.pk}/invoicing/invoices/').status_code == 403


def test_invalid_source_lines_dates_replay_and_csrf(finance):
    client, _, company, other, product, partner, location = finance
    order = create(client, company, payload(product, partner, location)); action(client, company, order, 'confirm')
    source = invoice_body(partner, sales_order_id=order['id'], order_version=1)
    # Une facture de commande ne peut pas injecter une ligne libre.
    assert post(client, f'companies/{company.pk}/invoicing/invoices/', source).status_code == 400
    source['lines'] = [{'sales_order_line_id': order['lines'][0]['id'], 'quantity': '1'}]
    source['order_version'] = 2
    assert post(client, f'companies/{company.pk}/invoicing/invoices/', source).status_code == 409
    bad = invoice_body(partner, due_date='2026-11-16')
    assert post(client, f'companies/{company.pk}/invoicing/invoices/', bad).status_code == 400
    body = invoice_body(partner); invoice = save(client, company, body)
    body['notes'] = 'Différent'
    assert post(client, f'companies/{company.pk}/invoicing/invoices/', body).status_code == 400
    assert client.post(f'/api/v1/companies/{company.pk}/invoicing/invoices/{invoice["id"]}/validate/', data='{}', content_type='application/json').status_code == 403
    validate(client, company, invoice)
    foreign = {**credit_body(invoice), 'request_key': str(uuid.uuid4())}
    assert post(client, f'companies/{other.pk}/invoicing/credit-notes/', foreign).status_code == 404
    another = save(client, company, invoice_body(partner)); validate(client, company, another)
    foreign['invoice_id'] = another['id']
    assert post(client, f'companies/{company.pk}/invoicing/credit-notes/', foreign).status_code == 400


def test_direct_catalog_price_is_frozen_and_draft_cancellation_replays(finance):
    client, _, company, _, product, partner, _ = finance
    body = invoice_body(partner, lines=[{'product_id': str(product.pk), 'quantity': '3'}])
    invoice = save(client, company, body)
    assert Decimal(invoice['lines'][0]['unit_price']) == Decimal('.335')
    product.sale_price = '900'; product.save()
    result = validate(client, company, invoice)
    assert result.status_code == 200 and Decimal(result.json()['lines'][0]['unit_price']) == Decimal('.335')
    draft = save(client, company, invoice_body(partner))
    url = f'companies/{company.pk}/invoicing/invoices/{draft["id"]}/cancel/'
    assert post(client, url, {}).status_code == 200 and post(client, url, {}).status_code == 200
    assert validate(client, company, draft).status_code == 400


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize('credit_mode', [False, True])
def test_concurrent_documents_and_replay(finance, credit_mode):
    client, user, company, _, product, partner, location = finance
    order = create(client, company, payload(product, partner, location, quantity='5')); action(client, company, order, 'confirm')
    body = invoice_body(partner, sales_order_id=order['id'], order_version=1, lines=[{'sales_order_line_id': order['lines'][0]['id'], 'quantity': '4'}])
    if credit_mode:
        parent = save(client, company, body); validate(client, company, parent)
        documents = [save(client, company, credit_body(parent, '3'), 'credit-notes') for _ in range(2)]
        kind, model = 'credit-notes', CreditNote
    else:
        documents = [save(client, company, {**body, 'request_key': str(uuid.uuid4())}) for _ in range(2)]
        kind, model = 'invoices', Invoice
    def work(document):
        from rest_framework.exceptions import ValidationError
        close_old_connections()
        try: document_action(user, company.pk, kind, document['id'], 'validate'); return 'ok'
        except ValidationError: return 'rejected'
        finally: close_old_connections()
    with ThreadPoolExecutor(max_workers=2) as pool: assert sorted(pool.map(work, documents)) == ['ok', 'rejected']
    winner = next(obj for obj in documents if model.objects.get(pk=obj['id']).status == 'validated')
    with ThreadPoolExecutor(max_workers=2) as pool: assert list(pool.map(work, [winner, winner])) == ['ok', 'ok']
    assert model.objects.filter(status='validated').count() == 1
