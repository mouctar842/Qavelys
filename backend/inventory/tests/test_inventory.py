import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
import pytest
from django.db import IntegrityError, close_old_connections, transaction
from django.test import Client
from core.models import CompanyModule, Module, RolePermission, User
from core.services import create_company
from inventory.models import Warehouse, StockLocation, StockBalance, StockMovement, StockTransfer
from reference.models import Product, UnitOfMeasure

pytestmark = pytest.mark.django_db


def post(client, path, data):
    token = client.get('/api/v1/auth/csrf/').json()['csrfToken']
    return client.post('/api/v1/' + path, data=json.dumps(data), content_type='application/json', HTTP_X_CSRFTOKEN=token)


@pytest.fixture
def setup():
    user = User.objects.create_user('inventory@example.com', 'Long-password!2026', full_name='Magasinier', email_verified=True)
    company = create_company(user, uuid.uuid4(), {'name': 'Stock A', 'country_code': 'GN', 'currency_code': 'GNF'})[0]
    other = create_company(user, uuid.uuid4(), {'name': 'Stock B', 'country_code': 'FR', 'currency_code': 'EUR'})[0]
    module, _ = Module.objects.get_or_create(code='inventory', defaults={'name': 'Inventaire', 'status': 'available'})
    for current in (company, other): CompanyModule.objects.create(company=current, module=module, enabled=True)
    unit, _ = UnitOfMeasure.objects.get_or_create(symbol='u', defaults={'name': 'Unité', 'category': 'count'})
    product = Product.objects.create(company=company, name='Article', sku='ART', unit=unit, type='stockable')
    source = StockLocation.objects.get(company=company, type='internal')
    warehouse = Warehouse.objects.create(company=company, name='Secondaire', code='SEC')
    destination = StockLocation.objects.create(company=company, warehouse=warehouse, name='Stock')
    client = Client(enforce_csrf_checks=True); client.force_login(user)
    return client, user, company, other, product, source, destination


def adjustment(client, base, product, source, quantity='10.125000'):
    return post(client, base + 'adjustments/', {'request_key': str(uuid.uuid4()), 'location_id': str(source.id), 'reason': 'Inventaire physique', 'lines': [{'product_id': str(product.id), 'counted_quantity': quantity}]})


def transfer(client, base, product, source, destination, quantity='4.125000', key=None):
    return post(client, base + 'transfers/', {'request_key': str(key or uuid.uuid4()), 'product_id': str(product.id), 'source_location_id': str(source.id), 'destination_location_id': str(destination.id), 'quantity': quantity})


def test_onboarding_and_structure(setup):
    client, _, company, _, _, source, _ = setup
    base = f'companies/{company.id}/inventory/'
    assert StockLocation.objects.filter(company=company, warehouse=None).count() == 3
    response = post(client, base + 'warehouses/', {'name': 'Nord', 'code': 'NORD'})
    assert response.status_code == 201
    assert StockLocation.objects.filter(company=company, warehouse_id=response.json()['id'], type='internal').count() == 1
    assert post(client, base + 'warehouses/', {'name': 'Doublon', 'code': 'NORD'}).status_code == 400
    assert post(client, base + f'locations/{source.id}/update/', {'warehouse_id': response.json()['id']}).status_code == 400


def test_adjustment_transfer_and_repeated_validation(setup):
    client, _, company, _, product, source, destination = setup
    base = f'companies/{company.id}/inventory/'
    adj = adjustment(client, base, product, source)
    assert adj.status_code == 201
    assert not StockBalance.objects.filter(company=company).exists()
    for _ in range(2): assert post(client, base + f'adjustments/{adj.json()["id"]}/validate/', {}).status_code == 200
    key = uuid.uuid4()
    first = transfer(client, base, product, source, destination, key=key)
    replay = transfer(client, base, product, source, destination, key=key)
    assert first.status_code == 201 and replay.status_code == 200 and first.json()['id'] == replay.json()['id']
    assert transfer(client, base, product, source, destination, quantity='9', key=key).status_code == 400
    for _ in range(2): assert post(client, base + f'transfers/{first.json()["id"]}/validate/', {}).status_code == 200
    assert StockMovement.objects.filter(company=company).count() == 2
    assert StockBalance.objects.get(company=company, product=product, location=source).quantity == Decimal('6')
    assert StockBalance.objects.get(company=company, product=product, location=destination).quantity == Decimal('4.125')
    assert post(client, base + f'transfers/{first.json()["id"]}/cancel/', {}).status_code == 400
    assert client.get('/api/v1/' + base + 'movements/').json()['count'] == 2


def test_reserved_stock_and_rollback(setup):
    client, _, company, _, product, source, destination = setup
    base = f'companies/{company.id}/inventory/'
    StockBalance.objects.create(company=company, product=product, location=source, quantity=10, reserved_quantity=7)
    doc = transfer(client, base, product, source, destination, quantity='4').json()
    assert post(client, base + f'transfers/{doc["id"]}/validate/', {}).status_code == 400
    assert not StockBalance.objects.filter(location=destination).exists()
    assert not StockMovement.objects.exists()
    adj = adjustment(client, base, product, source, quantity='6').json()
    assert post(client, base + f'adjustments/{adj["id"]}/validate/', {}).status_code == 400
    assert StockBalance.objects.get(location=source).quantity == 10
    assert post(client, base + f'locations/{source.id}/archive/', {}).status_code == 400
    with pytest.raises(IntegrityError), transaction.atomic(): StockBalance.objects.filter(location=source).update(quantity=6)


def test_foreign_ids_services_and_permissions(setup):
    client, _, company, other, product, source, destination = setup
    base = f'companies/{company.id}/inventory/'
    foreign = StockLocation.objects.get(company=other, type='internal')
    assert transfer(client, base, product, source, foreign).status_code == 400
    assert client.get('/api/v1/' + base + f'locations/{foreign.id}/').status_code == 404
    with pytest.raises(IntegrityError), transaction.atomic():
        StockBalance.objects.create(company=company, product=product, location=foreign)
    product.type = 'service'; product.save()
    assert transfer(client, base, product, source, destination).status_code == 400
    RolePermission.objects.filter(role__company=company, permission_id='inventory.adjustment.create').delete()
    assert adjustment(client, base, product, source).status_code == 403
    CompanyModule.objects.filter(company=company, module__code='inventory').update(enabled=False)
    assert client.get('/api/v1/' + base + 'balances/').status_code == 403


def test_product_unit_and_stock_nature_are_preserved_after_stock_history(setup):
    client, _, company, _, product, source, _ = setup
    catalog, _ = Module.objects.get_or_create(code='catalog', defaults={'name': 'Catalogue', 'status': 'available'})
    CompanyModule.objects.get_or_create(company=company, module=catalog, defaults={'enabled': True})
    StockBalance.objects.create(company=company, product=product, location=source, quantity=10)
    other_unit, _ = UnitOfMeasure.objects.get_or_create(symbol='kg', defaults={'name': 'Kilogramme', 'category': 'weight'})
    base = f'companies/{company.id}/reference/products/{product.id}/update/'
    assert post(client, base, {'unit_id': str(other_unit.id)}).status_code == 400
    assert post(client, base, {'type': 'service'}).status_code == 400
    assert post(client, base, {'sale_price': '25.123456'}).status_code == 200
    product.refresh_from_db()
    assert product.type == 'stockable' and product.unit_id != other_unit.id


@pytest.mark.django_db(transaction=True)
def test_concurrent_transfers_cannot_overdraw(setup):
    _, user, company, _, product, source, destination = setup
    from core.administration import locked_company
    from inventory.services import validate_transfer
    StockBalance.objects.create(company=company, product=product, location=source, quantity=10)
    docs = [StockTransfer.objects.create(company=company, created_by=user, reference=f'TRF-TEST-{i}', request_key=uuid.uuid4(), payload_hash='test-only', product=product, source_location=source, destination_location=destination, quantity=7) for i in range(2)]
    def work(pk):
        close_old_connections()
        try:
            with transaction.atomic():
                current = locked_company(user, company.id, 'inventory.transfer.validate')
                validate_transfer(current, user, StockTransfer.objects.get(pk=pk))
            return 'ok'
        except Exception as error:
            from rest_framework.exceptions import ValidationError
            if isinstance(error, ValidationError): return 'insufficient'
            raise
        finally: close_old_connections()
    with ThreadPoolExecutor(max_workers=2) as pool: results = list(pool.map(work, [item.pk for item in docs]))
    assert sorted(results) == ['insufficient', 'ok']
    assert StockBalance.objects.get(location=source).quantity == 3
    assert StockBalance.objects.get(location=destination).quantity == 7
    assert StockMovement.objects.count() == 1
    validated_id = StockTransfer.objects.get(status='validated').pk
    with ThreadPoolExecutor(max_workers=2) as pool: repeated = list(pool.map(work, [validated_id, validated_id]))
    assert repeated == ['ok', 'ok']
    assert StockBalance.objects.get(location=source).quantity == 3
    assert StockMovement.objects.count() == 1
