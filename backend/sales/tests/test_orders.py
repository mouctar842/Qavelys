import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
import pytest
from django.db import IntegrityError, transaction, close_old_connections
from django.test import Client
from core.models import CompanyModule, Module, Role, RolePermission, Membership, MembershipRole, User
from core.services import create_company
from inventory.models import StockBalance, StockLocation, StockReservation
from reference.models import Partner, Product, UnitOfMeasure
from sales.models import SalesOrder, SalesOrderLine
from approvals.models import ApprovalRequest, ApprovalDecision

pytestmark = pytest.mark.django_db


def post(client, path, data):
    token = client.get('/api/v1/auth/csrf/').json()['csrfToken']
    return client.post('/api/v1/' + path, data=json.dumps(data), content_type='application/json', HTTP_X_CSRFTOKEN=token)


@pytest.fixture
def setup():
    user = User.objects.create_user('orders@example.com', 'Long-password!2026', full_name='Administrateur', email_verified=True)
    company = create_company(user, uuid.uuid4(), {'name': 'Commerce A', 'country_code': 'FR', 'currency_code': 'EUR'})[0]
    other = create_company(user, uuid.uuid4(), {'name': 'Commerce B', 'country_code': 'GN', 'currency_code': 'GNF'})[0]
    for code in ['sales', 'purchases', 'catalog', 'contacts', 'inventory', 'crm']:
        module, _ = Module.objects.get_or_create(code=code, defaults={'name': code, 'status': 'available'})
        for current in (company, other): CompanyModule.objects.get_or_create(company=current, module=module, defaults={'enabled': True})
    unit, _ = UnitOfMeasure.objects.get_or_create(symbol='u', defaults={'name': 'Unité', 'category': 'count'})
    product = Product.objects.create(company=company, name='Article', sku='ART', unit=unit, type='stockable', sale_price='0.335', cost_price='0.2')
    partner = Partner.objects.create(company=company, name='Client fournisseur', is_customer=True, is_supplier=True)
    location = StockLocation.objects.get(company=company, type='internal')
    client = Client(enforce_csrf_checks=True); client.force_login(user)
    return client, user, company, other, product, partner, location


def payload(product, partner, location, quantity='3', **extra):
    return {'request_key': str(uuid.uuid4()), 'partner_id': str(partner.pk), 'warehouse_id': str(location.warehouse_id), 'order_date': '2026-11-16', 'lines': [{'product_id': str(product.pk), 'quantity': quantity, 'tax_rate': '20'}], **extra}


def create(client, company, body, domain='sales'):
    response = post(client, f'companies/{company.pk}/{domain}/orders/', body)
    assert response.status_code == 201, response.content
    return response.json()


def action(client, company, order, verb, domain='sales'):
    return post(client, f'companies/{company.pk}/{domain}/orders/{order["id"]}/{verb}/', {'version': order['version']})


def rule(client, company, kind='sales_order', minimum='1', maximum=None, role_id=None):
    role_id = role_id or Role.objects.get(company=company, is_system=True).pk
    response = post(client, f'companies/{company.pk}/approvals/rules/', {'document_type': kind, 'min_amount': minimum, 'max_amount': maximum, 'approver_role_id': str(role_id), 'active': True})
    assert response.status_code == 201, response.content
    return response.json()


def test_totals_snapshots_replay_and_float_rejection(setup):
    client, _, company, _, product, partner, location = setup
    body = payload(product, partner, location)
    # Trois lignes illustrent la différence avec l’arrondi intermédiaire.
    body['lines'] = [{'product_id': str(product.pk), 'quantity': '1', 'tax_rate': '20'} for _ in range(3)]
    order = create(client, company, body)
    assert Decimal(order['untaxed_amount']) == Decimal('1.01') and Decimal(order['tax_amount']) == Decimal('.20')
    assert Decimal(order['total_amount']) == Decimal('1.21')
    assert post(client, f'companies/{company.pk}/sales/orders/', body).status_code == 200
    assert SalesOrder.objects.count() == 1
    product.sale_price = 99; product.save()
    assert Decimal(client.get(f'/api/v1/companies/{company.pk}/sales/orders/{order["id"]}/').json()['lines'][0]['unit_price']) == Decimal('.335')
    body['request_key'] = str(uuid.uuid4()); body['lines'][0]['unit_price'] = 0.335
    assert post(client, f'companies/{company.pk}/sales/orders/', body).status_code == 400


def test_confirmation_partial_reservation_and_cancel_releases(setup):
    client, _, company, _, product, partner, location = setup
    StockBalance.objects.create(company=company, product=product, location=location, quantity=2)
    order = create(client, company, payload(product, partner, location, quantity='5'))
    for _ in range(2): response = action(client, company, order, 'confirm'); assert response.status_code == 200
    assert response.json()['lines'][0]['reserved_quantity'] == '2.000000'
    assert Decimal(response.json()['lines'][0]['waiting_quantity']) == 3
    balance = StockBalance.objects.get(location=location); assert balance.quantity == 2 and balance.reserved_quantity == 2
    assert StockReservation.objects.count() == 1
    assert action(client, company, order, 'reserve').status_code == 200
    assert StockReservation.objects.get().quantity == 2
    adjustment = post(client, f'companies/{company.pk}/inventory/adjustments/', {'request_key': str(uuid.uuid4()), 'location_id': str(location.pk), 'reason': 'Nouveau comptage', 'lines': [{'product_id': str(product.pk), 'counted_quantity': '10'}]}).json()
    assert post(client, f'companies/{company.pk}/inventory/adjustments/{adjustment["id"]}/validate/', {}).status_code == 200
    assert action(client, company, order, 'reserve').status_code == 200
    assert StockReservation.objects.get().quantity == 5
    for _ in range(2): assert action(client, company, order, 'cancel').status_code == 200
    balance.refresh_from_db(); assert balance.reserved_quantity == 0 and balance.quantity == 10
    assert StockReservation.objects.get().status == 'released'


def test_approval_required_decision_replay_and_revision_invalidates(setup):
    client, _, company, _, product, partner, location = setup
    rule(client, company)
    body = payload(product, partner, location)
    order = create(client, company, body)
    assert action(client, company, order, 'confirm').status_code == 400
    for _ in range(2): assert action(client, company, order, 'submit').status_code == 200
    assert ApprovalRequest.objects.count() == 1
    approval = ApprovalRequest.objects.get()
    for _ in range(2): assert post(client, f'companies/{company.pk}/approvals/requests/{approval.pk}/decide/', {'decision': 'approved', 'comment': 'Validé'}).status_code == 200
    assert ApprovalDecision.objects.count() == 1
    body['version'] = 1; body.pop('request_key')
    body['lines'][0]['quantity'] = '4'
    updated = post(client, f'companies/{company.pk}/sales/orders/{order["id"]}/update/', body)
    assert updated.status_code == 200 and updated.json()['version'] == 2
    assert SalesOrderLine.objects.count() == 2
    assert Decimal(updated.json()['approval_requests'][0]['total_amount']) == Decimal('1.21')
    approval.refresh_from_db(); assert approval.status == 'superseded'
    assert action(client, company, updated.json(), 'confirm').status_code == 400
    assert action(client, company, order, 'confirm').status_code == 409


def test_rule_overlap_boundaries_and_rule_changes(setup):
    client, _, company, _, product, partner, location = setup
    original = rule(client, company, minimum='0', maximum='1')
    rule(client, company, minimum='1', maximum=None)
    rejected = post(client, f'companies/{company.pk}/approvals/rules/', {'document_type': 'sales_order', 'min_amount': '.5', 'max_amount': '2', 'approver_role_id': original['approver_role_id'], 'active': True})
    assert rejected.status_code == 400
    order = create(client, company, payload(product, partner, location, quantity='1'))
    assert action(client, company, order, 'submit').status_code == 200
    original['active'] = False
    assert post(client, f'companies/{company.pk}/approvals/rules/{original["id"]}/update/', original).status_code == 200
    assert ApprovalRequest.objects.get().status == 'superseded'
    assert action(client, company, order, 'confirm').status_code == 200


def test_purchase_flow_and_rejection(setup):
    client, _, company, _, product, partner, location = setup
    rule(client, company, kind='purchase_order', minimum='0')
    order = create(client, company, payload(product, partner, location), domain='purchases')
    assert Decimal(order['lines'][0]['unit_price']) == Decimal('.2')
    assert action(client, company, order, 'submit', domain='purchases').status_code == 200
    approval = ApprovalRequest.objects.get()
    assert post(client, f'companies/{company.pk}/approvals/requests/{approval.pk}/decide/', {'decision': 'rejected', 'comment': 'À revoir'}).status_code == 200
    assert action(client, company, order, 'confirm', domain='purchases').status_code == 400
    assert action(client, company, order, 'submit', domain='purchases').status_code == 200
    assert ApprovalRequest.objects.count() == 2
    approval = ApprovalRequest.objects.get(status='pending')
    assert post(client, f'companies/{company.pk}/approvals/requests/{approval.pk}/decide/', {'decision': 'approved'}).status_code == 200
    assert action(client, company, order, 'confirm', domain='purchases').status_code == 200
    assert not StockReservation.objects.exists() and not StockBalance.objects.exists()


def test_cross_tenant_relations_and_role_decision(setup):
    client, user, company, other, product, partner, location = setup
    foreign = StockLocation.objects.get(company=other, type='internal')
    body = payload(product, partner, location); body['warehouse_id'] = str(foreign.warehouse_id)
    assert post(client, f'companies/{company.pk}/sales/orders/', body).status_code == 400
    foreign_role = Role.objects.get(company=other, is_system=True)
    assert post(client, f'companies/{company.pk}/approvals/rules/', {'document_type': 'sales_order', 'min_amount': '0', 'max_amount': None, 'approver_role_id': str(foreign_role.pk), 'active': True}).status_code == 400
    order = create(client, company, payload(product, partner, location))
    assert client.get(f'/api/v1/companies/{other.pk}/sales/orders/{order["id"]}/').status_code == 404
    with pytest.raises(IntegrityError), transaction.atomic(): SalesOrder.objects.filter(pk=order['id']).update(warehouse_id=foreign.warehouse_id)
    # Le droit décider seul ne remplace jamais le rôle affecté à la règle.
    approver_role = Role.objects.create(company=company, name='Direction')
    extra_user = User.objects.create_user('direction@example.com', 'Long-password!2026', email_verified=True)
    member = Membership.objects.create(company=company, user=extra_user)
    MembershipRole.objects.create(company=company, membership=member, role=approver_role)
    rule(client, company, role_id=approver_role.pk)
    action(client, company, order, 'submit')
    approval = ApprovalRequest.objects.get()
    assert post(client, f'companies/{company.pk}/approvals/requests/{approval.pk}/decide/', {'decision': 'approved'}).status_code == 403


def test_crm_quote_and_services_do_not_reserve(setup):
    client, user, company, _, product, partner, location = setup
    from crm.models import Lead
    lead = Lead.objects.create(company=company, owner=Membership.objects.get(company=company, user=user), title='Prospect')
    product.type = 'service'; product.save()
    order = create(client, company, payload(product, partner, location, lead_id=str(lead.pk)))
    lead.refresh_from_db(); assert lead.partner == partner
    assert action(client, company, order, 'confirm').status_code == 200
    assert not StockReservation.objects.exists()


def test_permissions_modules_and_confirmed_immutability(setup):
    client, _, company, _, product, partner, location = setup
    body = payload(product, partner, location)
    order = create(client, company, body)
    assert action(client, company, order, 'confirm').status_code == 200
    body.pop('request_key'); body['version'] = 1
    assert post(client, f'companies/{company.pk}/sales/orders/{order["id"]}/update/', body).status_code == 400
    assert action(client, company, order, 'reopen').status_code == 400
    assert post(client, f'companies/{company.pk}/reference/products/{product.pk}/update/', {'type': 'service'}).status_code == 400
    RolePermission.objects.filter(role__company=company, permission_id='sales.order.create').delete()
    assert post(client, f'companies/{company.pk}/sales/orders/', payload(product, partner, location)).status_code == 403
    CompanyModule.objects.filter(company=company, module__code='sales').update(enabled=False)
    assert client.get(f'/api/v1/companies/{company.pk}/sales/orders/').status_code == 403


@pytest.mark.django_db(transaction=True)
def test_concurrent_orders_cannot_overreserve(setup):
    client, user, company, _, product, partner, location = setup
    from core.orders import order_action
    StockBalance.objects.create(company=company, product=product, location=location, quantity=5)
    orders = [create(client, company, payload(product, partner, location, quantity='4')) for _ in range(2)]
    def work(order):
        close_old_connections()
        try: order_action(user, company.pk, 'sales', order['id'], 'confirm', 1)
        finally: close_old_connections()
    with ThreadPoolExecutor(max_workers=2) as pool: list(pool.map(work, orders))
    assert StockBalance.objects.get(location=location).reserved_quantity == 5
    assert sum(StockReservation.objects.values_list('quantity', flat=True)) == 5
    with ThreadPoolExecutor(max_workers=2) as pool: list(pool.map(work, orders))
    assert sum(StockReservation.objects.values_list('quantity', flat=True)) == 5
