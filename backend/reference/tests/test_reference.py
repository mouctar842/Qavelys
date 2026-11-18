import json
import uuid
from decimal import Decimal
import pytest
from django.db import IntegrityError, transaction
from django.test import Client
from core.models import CompanyModule, Module, RolePermission, User
from core.services import create_company
from core.money import document_totals, rounded
from reference.models import Partner, Product, ProductCategory, ProductPriceHistory, ProductTax, Tax, UnitOfMeasure

pytestmark = pytest.mark.django_db


def post(client, path, data):
    token = client.get('/api/v1/auth/csrf/').json()['csrfToken']
    return client.post('/api/v1/' + path, data=json.dumps(data), content_type='application/json', HTTP_X_CSRFTOKEN=token)


@pytest.fixture
def setup():
    owner = User.objects.create_user('catalog-owner@example.com', 'Long-password!2026', email_verified=True)
    company = create_company(owner, uuid.uuid4(), {'name': 'A', 'country_code': 'GN', 'currency_code': 'GNF'})[0]
    other = create_company(owner, uuid.uuid4(), {'name': 'B', 'country_code': 'FR', 'currency_code': 'EUR'})[0]
    for code in ('contacts', 'catalog'):
        module, _ = Module.objects.get_or_create(code=code, defaults={'name': code, 'status': 'available'})
        module.status = 'available'; module.save()
        CompanyModule.objects.get_or_create(company=company, module=module, defaults={'enabled': True})
        CompanyModule.objects.get_or_create(company=other, module=module, defaults={'enabled': True})
    unit, _ = UnitOfMeasure.objects.get_or_create(symbol='u', defaults={'name': 'Unité', 'category': 'count'})
    client = Client(enforce_csrf_checks=True); client.force_login(owner)
    return client, owner, company, other, unit


def test_partner_crud_archive_search_and_cross_company(setup):
    client, _, company, other, _ = setup
    base = f'companies/{company.id}/reference/partners/'
    created = post(client, base, {'name': 'Client réel', 'email': 'client@example.com', 'is_customer': True, 'is_supplier': True})
    assert created.status_code == 201
    partner_id = created.json()['id']
    assert post(client, base, {'name': 'Invalide', 'is_customer': False, 'is_supplier': False}).status_code == 400
    assert client.get('/api/v1/' + base + '?search=client&kind=supplier').json()['count'] == 1
    assert client.get(f'/api/v1/companies/{other.id}/reference/partners/{partner_id}/').status_code == 404
    assert post(client, base + partner_id + '/update/', {'phone': '+224123'}).json()['phone'] == '+224123'
    assert post(client, base + partner_id + '/archive/', {}).status_code == 200
    assert client.get('/api/v1/' + base).json()['count'] == 0
    assert client.get('/api/v1/' + base + '?state=archived').json()['count'] == 1
    assert Partner.objects.filter(pk=partner_id).exists()
    assert post(client, base + partner_id + '/restore/', {}).status_code == 200


def test_products_relations_history_and_sku_scope(setup):
    client, _, company, other, unit = setup
    base = f'companies/{company.id}/reference/'
    category = post(client, base + 'categories/', {'name': 'Catégorie'}).json()
    tax = post(client, base + 'taxes/', {'name': 'Taxe', 'rate': '18.0000'}).json()
    data = {'sku': 'sku-a', 'name': 'Produit', 'type': 'stockable', 'unit_id': str(unit.id), 'category_id': category['id'], 'sale_price': '100.125000', 'cost_price': '75.000000', 'tax_ids': [tax['id']]}
    created = post(client, base + 'products/', data)
    assert created.status_code == 201
    product = created.json(); assert product['sku'] == 'SKU-A'
    assert product['sale_price'] == '100.125000'
    assert post(client, base + 'products/', data).status_code == 400
    data['category_id'] = None; data['tax_ids'] = []
    assert post(client, f'companies/{other.id}/reference/products/', data).status_code == 201
    assert post(client, base + f'products/{product["id"]}/update/', {'sale_price': '101.125000'}).status_code == 200
    assert ProductPriceHistory.objects.get(product_id=product['id']).old_sale_price == Decimal('100.125000')
    assert len(client.get('/api/v1/' + base + f'products/{product["id"]}/price-history/').json()) == 1
    foreign = ProductCategory.objects.create(company=other, name='Extérieure')
    assert post(client, base + f'products/{product["id"]}/update/', {'category_id': str(foreign.id)}).status_code == 400
    assert post(client, base + f'products/{product["id"]}/update/', {'sale_price': '-1'}).status_code == 400
    product_obj = Product.objects.get(pk=product['id'])
    foreign_tax = Tax.objects.create(company=other, name='Étrangère', rate='10')
    with pytest.raises(IntegrityError), transaction.atomic():
        ProductTax.objects.create(company=company, product=product_obj, tax=foreign_tax)


def test_category_cycles_module_and_permissions(setup):
    client, _, company, _, _ = setup
    base = f'companies/{company.id}/reference/'
    first = post(client, base + 'categories/', {'name': 'A'}).json()
    second = post(client, base + 'categories/', {'name': 'B', 'parent_id': first['id']}).json()
    assert post(client, base + f'categories/{first["id"]}/update/', {'parent_id': second['id']}).status_code == 400
    RolePermission.objects.filter(role__company=company, permission_id='contacts.manage').delete()
    assert post(client, base + 'partners/', {'name': 'Refusé'}).status_code == 403
    CompanyModule.objects.filter(company=company, module__code='catalog').update(enabled=False)
    for resource in ('products', 'categories', 'taxes', 'units'):
        assert client.get('/api/v1/' + base + resource + '/').status_code == 403


def test_pagination_ordering_and_invalid_identifiers(setup):
    client, _, company, _, _ = setup
    Partner.objects.bulk_create([Partner(company=company, name=f'Client {i:02d}') for i in range(30)])
    base = f'companies/{company.id}/reference/partners/'
    page = client.get('/api/v1/' + base + '?page=2&page_size=10&ordering=-name').json()
    assert page['count'] == 30 and len(page['results']) == 10
    assert page['results'][0]['name'] == 'Client 19'
    assert client.get('/api/v1/' + base + '?ordering=password').status_code == 400
    assert client.get('/api/v1/' + base + '?page=invalid').status_code == 400


def test_financial_rounding_is_at_document_total():
    lines = [{'quantity': '1', 'unit_price': '0.335', 'tax_rate': '20'}] * 3
    totals = document_totals(lines, 'EUR')
    assert totals == {'untaxed_amount': Decimal('1.01'), 'tax_amount': Decimal('0.20'), 'total_amount': Decimal('1.21')}
    assert totals['untaxed_amount'] != Decimal('0.34') * 3
    assert rounded('1.5', 'GNF') == Decimal('2')
    assert rounded('1.2345', 'TND') == Decimal('1.235')
