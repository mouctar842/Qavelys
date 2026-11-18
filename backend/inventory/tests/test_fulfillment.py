import uuid
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
import pytest
from django.db import IntegrityError, transaction, close_old_connections
from core.models import CompanyModule, RolePermission
from inventory.models import StockBalance, StockMovement, StockReservation, Delivery, GoodsReceipt, DeliveryLine, StockLocation
from inventory.fulfillment import document_action
from sales.tests.test_orders import setup, post, payload, create, action

pytestmark = pytest.mark.django_db


def document(client, company, order, location, quantity, kind='receipts', **extra):
    body = {'request_key': str(uuid.uuid4()), 'order_id': order['id'], 'version': order['version'], 'location_id': str(location.pk), 'lines': [{'order_line_id': order['lines'][0]['id'], 'quantity': quantity}], **extra}
    response = post(client, f'companies/{company.pk}/inventory/{kind}/', body)
    assert response.status_code == 201, response.content
    return response.json(), body


def validate(client, company, obj, kind='receipts'):
    return post(client, f'companies/{company.pk}/inventory/{kind}/{obj["id"]}/validate/', {})


def detail(client, company, order, domain='sales'):
    return client.get(f'/api/v1/companies/{company.pk}/{domain}/orders/{order["id"]}/').json()


def test_partial_receipts_and_deliveries_replay_and_remaining(setup):
    client, _, company, _, product, partner, location = setup
    purchase = create(client, company, payload(product, partner, location, quantity='5'), 'purchases')
    assert action(client, company, purchase, 'confirm', 'purchases').status_code == 200
    receipt, body = document(client, company, purchase, location, '2')
    assert not StockBalance.objects.exists()
    replay = post(client, f'companies/{company.pk}/inventory/receipts/', body)
    assert replay.status_code == 200 and replay.json()['id'] == receipt['id']
    assert validate(client, company, receipt).status_code == 200
    assert validate(client, company, receipt).status_code == 200
    sale = create(client, company, payload(product, partner, location, quantity='5'))
    assert action(client, company, sale, 'confirm').status_code == 200
    delivery, _ = document(client, company, sale, location, '2', 'deliveries')
    assert validate(client, company, delivery, 'deliveries').status_code == 200
    assert validate(client, company, delivery, 'deliveries').status_code == 200
    balance = StockBalance.objects.get(product=product); assert balance.quantity == 0 and balance.reserved_quantity == 0
    line = detail(client, company, sale)['lines'][0]
    assert Decimal(line['fulfilled_quantity']) == 2 and Decimal(line['waiting_quantity']) == 3
    second, _ = document(client, company, purchase, location, '3')
    assert validate(client, company, second).status_code == 200
    assert action(client, company, sale, 'reserve').status_code == 200
    reservation = StockReservation.objects.get(); assert reservation.quantity == 3 and reservation.fulfilled_quantity == 2 and reservation.status == 'active'
    delivery2, _ = document(client, company, sale, location, '3', 'deliveries')
    assert validate(client, company, delivery2, 'deliveries').status_code == 200
    assert action(client, company, sale, 'reserve').status_code == 200
    assert detail(client, company, sale)['fulfillment_status'] == 'done'
    assert detail(client, company, purchase, 'purchases')['fulfillment_status'] == 'done'
    assert not StockReservation.objects.filter(status='active').exists()
    balance.refresh_from_db(); assert balance.quantity == 0 and balance.reserved_quantity == 0
    assert StockMovement.objects.count() == 4
    assert action(client, company, sale, 'cancel').status_code == 400
    assert action(client, company, purchase, 'cancel', 'purchases').status_code == 400
    movements = client.get(f'/api/v1/companies/{company.pk}/inventory/movements/').json()['results']
    assert {row['reference'] for row in movements} == {receipt['reference'], second['reference'], delivery['reference'], delivery2['reference']}


def test_cumulative_overflow_rolls_back_and_validated_is_immutable(setup):
    client, _, company, _, product, partner, location = setup
    order = create(client, company, payload(product, partner, location, quantity='5'), 'purchases')
    action(client, company, order, 'confirm', 'purchases')
    one, _ = document(client, company, order, location, '4')
    two, _ = document(client, company, order, location, '4')
    assert validate(client, company, one).status_code == 200
    assert validate(client, company, two).status_code == 400
    assert StockBalance.objects.get().quantity == 4 and StockMovement.objects.count() == 1
    assert GoodsReceipt.objects.get(pk=two['id']).status == 'draft'
    assert post(client, f'companies/{company.pk}/inventory/receipts/{one["id"]}/cancel/', {}).status_code == 400
    assert post(client, f'companies/{company.pk}/inventory/receipts/{two["id"]}/cancel/', {}).status_code == 200
    assert validate(client, company, two).status_code == 400


def test_delivery_preserves_other_reservations_and_location_scope(setup):
    client, _, company, _, product, partner, location = setup
    StockBalance.objects.create(company=company, product=product, location=location, quantity=5)
    other = create(client, company, payload(product, partner, location, quantity='4')); action(client, company, other, 'confirm')
    sale = create(client, company, payload(product, partner, location, quantity='4')); action(client, company, sale, 'confirm')
    delivery, _ = document(client, company, sale, location, '2', 'deliveries')
    assert validate(client, company, delivery, 'deliveries').status_code == 400
    balance = StockBalance.objects.get(); assert balance.quantity == 5 and balance.reserved_quantity == 5
    assert not StockMovement.objects.exists()
    wrong = StockLocation.objects.create(company=company, warehouse=location.warehouse, name='Autre')
    delivery2, _ = document(client, company, other, wrong, '1', 'deliveries')
    assert validate(client, company, delivery2, 'deliveries').status_code == 400
    assert not StockBalance.objects.filter(location=wrong).exists()  # création de solde annulée avec la transaction


def test_service_execution_without_stock_and_cancellation_before_effect(setup):
    client, _, company, _, product, partner, location = setup
    product.type = 'service'; product.save()
    for domain, kind in [('sales', 'deliveries'), ('purchases', 'receipts')]:
        order = create(client, company, payload(product, partner, location), domain); action(client, company, order, 'confirm', domain)
        obj, _ = document(client, company, order, location, '3', kind)
        assert validate(client, company, obj, kind).status_code == 200
        assert detail(client, company, order, domain)['fulfillment_status'] == 'done'
        assert action(client, company, order, 'cancel', domain).status_code == 400
    assert not StockMovement.objects.exists() and not StockBalance.objects.exists() and not StockReservation.objects.exists()
    order = create(client, company, payload(product, partner, location)); action(client, company, order, 'confirm')
    obj, _ = document(client, company, order, location, '1', 'deliveries')
    assert action(client, company, order, 'cancel').status_code == 200
    assert validate(client, company, obj, 'deliveries').status_code == 400
    assert post(client, f'companies/{company.pk}/inventory/deliveries/{obj["id"]}/cancel/', {}).status_code == 200


def test_foreign_relations_permissions_modules_and_exact_quantities(setup):
    client, _, company, other, product, partner, location = setup
    order = create(client, company, payload(product, partner, location)); action(client, company, order, 'confirm')
    obj, body = document(client, company, order, location, '1', 'deliveries')
    foreign = StockLocation.objects.get(company=other, type='internal')
    bad = {**body, 'request_key': str(uuid.uuid4()), 'location_id': str(foreign.pk)}
    assert post(client, f'companies/{company.pk}/inventory/deliveries/', bad).status_code == 400
    bad = {**body, 'request_key': str(uuid.uuid4()), 'lines': [{'order_line_id': order['lines'][0]['id'], 'quantity': 1.5}]}
    assert post(client, f'companies/{company.pk}/inventory/deliveries/', bad).status_code == 400
    assert client.get(f'/api/v1/companies/{other.pk}/inventory/deliveries/{obj["id"]}/').status_code == 404
    with pytest.raises(IntegrityError), transaction.atomic(): Delivery.objects.filter(pk=obj['id']).update(location=foreign)
    RolePermission.objects.filter(role__company=company, permission_id='inventory.delivery.validate').delete()
    assert validate(client, company, obj, 'deliveries').status_code == 403
    CompanyModule.objects.filter(company=company, module__code='sales').update(enabled=False)
    assert client.get(f'/api/v1/companies/{company.pk}/inventory/deliveries/').status_code == 403


@pytest.mark.parametrize('kind,domain', [('receipts', 'purchases'), ('deliveries', 'sales')])
@pytest.mark.django_db(transaction=True)
def test_concurrent_execution_cannot_exceed_order_and_replay(setup, kind, domain):
    client, user, company, _, product, partner, location = setup
    if domain == 'sales': StockBalance.objects.create(company=company, product=product, location=location, quantity=5)
    order = create(client, company, payload(product, partner, location, quantity='5'), domain); action(client, company, order, 'confirm', domain)
    documents = [document(client, company, order, location, '4', kind)[0] for _ in range(2)]
    def work(obj):
        from rest_framework.exceptions import ValidationError
        close_old_connections()
        try:
            document_action(user, company.pk, kind, obj['id'], 'validate'); return 'ok'
        except ValidationError: return 'rejected'
        finally: close_old_connections()
    with ThreadPoolExecutor(max_workers=2) as pool: results = list(pool.map(work, documents))
    assert sorted(results) == ['ok', 'rejected']
    model = GoodsReceipt if kind == 'receipts' else Delivery
    winner = next(obj for obj in documents if model.objects.get(pk=obj['id']).status == 'validated')
    with ThreadPoolExecutor(max_workers=2) as pool: assert list(pool.map(work, [winner, winner])) == ['ok', 'ok']
    balance = StockBalance.objects.get()
    assert balance.quantity == (4 if domain == 'purchases' else 1) and StockMovement.objects.count() == 1
    if domain == 'sales': assert balance.reserved_quantity == 1


def test_multiline_delivery_rollback_and_wrong_order_line(setup):
    from reference.models import Product
    client, _, company, _, product, partner, location = setup
    second = Product.objects.create(company=company, name='Second', sku='TWO', unit=product.unit, type='stockable')
    body = payload(product, partner, location, quantity='1'); body['lines'].append({'product_id': str(second.pk), 'quantity': '1'})
    sale = create(client, company, body)
    StockBalance.objects.create(company=company, product=product, location=location, quantity=5)
    action(client, company, sale, 'confirm')
    content = {'request_key': str(uuid.uuid4()), 'order_id': sale['id'], 'version': 1, 'location_id': str(location.pk), 'lines': [{'order_line_id': line['id'], 'quantity': '1'} for line in sale['lines']]}
    response = post(client, f'companies/{company.pk}/inventory/deliveries/', content); assert response.status_code == 201
    assert validate(client, company, response.json(), 'deliveries').status_code == 400
    balance = StockBalance.objects.get(); assert balance.quantity == 5 and balance.reserved_quantity == 1
    assert not StockMovement.objects.exists()
    assert Delivery.objects.get().status == 'draft'
    other = create(client, company, payload(product, partner, location)); action(client, company, other, 'confirm')
    bad = {**content, 'request_key': str(uuid.uuid4()), 'lines': [{'order_line_id': other['lines'][0]['id'], 'quantity': '1'}]}
    assert post(client, f'companies/{company.pk}/inventory/deliveries/', bad).status_code == 400
    duplicate = {**content, 'request_key': str(uuid.uuid4()), 'lines': [content['lines'][0], content['lines'][0]]}
    assert post(client, f'companies/{company.pk}/inventory/deliveries/', duplicate).status_code == 400
