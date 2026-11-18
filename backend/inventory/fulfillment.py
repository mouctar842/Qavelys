import hashlib
import json
from decimal import Decimal
from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import NotFound, ValidationError
from core.administration import audit, locked_company, next_reference, require_module
from core.order_serializers import ExactDecimalField
from core.orders import get_order, current_lines, check_version, validate_confirmable
from core.services import require_membership
from .models import Delivery, DeliveryLine, GoodsReceipt, GoodsReceiptLine, StockLocation, StockMovement, StockReservation
from .services import internal_location, locked_balances


def config(kind):
    if kind == 'deliveries': return Delivery, DeliveryLine, 'sales', 'sales_order', 'delivery'
    if kind == 'receipts': return GoodsReceipt, GoodsReceiptLine, 'purchases', 'purchase_order', 'receipt'
    raise NotFound()


def access(user, company_id, kind, action='view', lock=False):
    _, _, domain, _, permission = config(kind)
    code = f'inventory.{permission}.{action}'
    company = locked_company(user, company_id, code) if lock else require_membership(user, company_id, code).company
    require_membership(user, company_id, f'inventory.{permission}.view')
    require_membership(user, company_id, f'{domain}.order.view')
    require_module(company_id, 'inventory'); require_module(company_id, domain)
    return company


def executed_quantities(order, domain):
    line_model = DeliveryLine if domain == 'sales' else GoodsReceiptLine
    return {row['order_line_id']: row['total'] for row in line_model.objects.filter(company_id=order.company_id, order_line__order=order, document__status='validated').values('order_line_id').annotate(total=Sum('quantity'))}


def has_validated_effects(order, domain):
    return (order.deliveries if domain == 'sales' else order.receipts).filter(status='validated').exists()


class FulfillmentLineInput(serializers.Serializer):
    order_line_id = serializers.UUIDField()
    quantity = ExactDecimalField(max_digits=20, decimal_places=6, min_value=Decimal('0.000001'))


class FulfillmentInput(serializers.Serializer):
    order_id = serializers.UUIDField()
    version = serializers.IntegerField(min_value=1)
    location_id = serializers.UUIDField()
    request_key = serializers.UUIDField()
    notes = serializers.CharField(allow_blank=True, default='', max_length=4000)
    lines = FulfillmentLineInput(many=True, allow_empty=False, max_length=200)


def checked_order_location(company, domain, order_id, version, location_id):
    order = get_order(company.id, domain, order_id)
    check_version(order, version)
    if order.status != 'confirmed': raise ValidationError('Une commande confirmée est requise.')
    validate_confirmable(company, order)
    location = internal_location(company.id, location_id)
    if location.warehouse_id != order.warehouse_id: raise ValidationError('Choisissez un emplacement de l’entrepôt de la commande.')
    return order, location


def check_lines(order, domain, lines):
    source = {line.pk: line for line in current_lines(order)}
    executed = executed_quantities(order, domain)
    ids = [line['order_line_id'] for line in lines]
    if not ids or len(ids) != len(set(ids)): raise ValidationError('Une à 200 lignes distinctes sont requises.')
    for line in lines:
        item = source.get(line['order_line_id'])
        if item is None: raise ValidationError('Ligne absente de la version confirmée de cette commande.')
        if line['quantity'] > item.quantity - executed.get(item.pk, Decimal(0)):
            raise ValidationError(f'Quantité restante dépassée pour {item.product_name}.')
    return source


@transaction.atomic
def create_document(user, company_id, kind, payload):
    company = access(user, company_id, kind, 'create', True)
    model, line_model, domain, order_field, sequence = config(kind)
    serializer = FulfillmentInput(data=payload); serializer.is_valid(raise_exception=True)
    data = dict(serializer.validated_data)
    fingerprint = hashlib.sha256(json.dumps(data, sort_keys=True, cls=DjangoJSONEncoder).encode()).hexdigest()
    previous = model.objects.filter(company=company, request_key=data['request_key']).first()
    if previous:
        if previous.payload_hash != fingerprint: raise ValidationError('Clé de création déjà utilisée avec un contenu différent.')
        return previous, False
    order, location = checked_order_location(company, domain, data['order_id'], data['version'], data['location_id'])
    check_lines(order, domain, data['lines'])
    obj = model.objects.create(company=company, **{order_field: order}, order_version=order.version, location=location, request_key=data['request_key'], payload_hash=fingerprint, notes=data['notes'], reference=next_reference(company, sequence), created_by=user)
    line_model.objects.bulk_create([line_model(company=company, document=obj, order_line_id=line['order_line_id'], quantity=line['quantity']) for line in data['lines']])
    audit(company, user, f'inventory.{sequence}_created', obj, after={'reference': obj.reference, 'order_id': order.pk})
    return obj, True


@transaction.atomic
def document_action(user, company_id, kind, pk, action):
    if action not in ('validate', 'cancel'): raise NotFound()
    company = access(user, company_id, kind, action, True)
    model, _, domain, order_field, sequence = config(kind)
    obj = model.objects.select_related(order_field, 'location').filter(company=company, pk=pk).first()
    if obj is None: raise NotFound()
    if action == 'cancel':
        if obj.status == 'validated': raise ValidationError('Un document validé nécessite une correction traçable.')
        if obj.status != 'cancelled':
            obj.status = 'cancelled'; obj.save(update_fields=['status', 'updated_at'])
            audit(company, user, f'inventory.{sequence}_cancelled', obj, after={'reference': obj.reference})
        return obj
    if obj.status == 'validated': return obj
    if obj.status != 'draft': raise ValidationError('Ce document ne peut plus être validé.')
    order, location = checked_order_location(company, domain, getattr(obj, order_field + '_id'), obj.order_version, obj.location_id)
    lines = list(obj.lines.select_related('order_line__product').order_by('order_line_id'))
    source = check_lines(order, domain, [{'order_line_id': line.order_line_id, 'quantity': line.quantity} for line in lines])
    physical = [line for line in lines if source[line.order_line_id].product_type != 'service']
    if domain == 'sales' and physical:
        from sales.reservations import reserve_order
        reserve_order(company, user, order)
    balances = locked_balances(company, [(source[line.order_line_id].product_id, location.pk) for line in physical]) if physical else {}
    logical = None
    if physical:
        logical = StockLocation.objects.filter(company=company, warehouse=None, type='customer' if domain == 'sales' else 'supplier', active=True).first()
        if logical is None: raise ValidationError('Emplacement logique actif introuvable.')
    now = timezone.now()
    for line in physical:
        item = source[line.order_line_id]
        balance = balances[(item.product_id, location.pk)]
        if domain == 'sales':
            reservation = StockReservation.objects.select_for_update().filter(company=company, sales_order_line=item, location=location, status='active').first()
            if reservation is None or reservation.quantity < line.quantity or balance.reserved_quantity < line.quantity or balance.quantity < line.quantity:
                raise ValidationError(f'Stock réservé insuffisant à cet emplacement pour {item.product_name}. Réservez ou réapprovisionnez cet emplacement.')
            reservation.quantity -= line.quantity; reservation.fulfilled_quantity += line.quantity
            if reservation.quantity == 0: reservation.status = 'fulfilled'
            reservation.save(update_fields=['quantity', 'fulfilled_quantity', 'status', 'updated_at'])
            balance.quantity -= line.quantity; balance.reserved_quantity -= line.quantity
            audit(company, user, 'inventory.reservation_consumed', reservation, after={'delivery_id': obj.pk, 'quantity': line.quantity})
        else:
            if balance.quantity + line.quantity >= Decimal('100000000000000'): raise ValidationError('Quantité maximale dépassée.')
            balance.quantity += line.quantity
        balance.save(update_fields=['quantity', 'reserved_quantity', 'updated_at'])
        StockMovement.objects.create(company=company, product_id=item.product_id, source_location=location if domain == 'sales' else logical, destination_location=logical if domain == 'sales' else location, quantity=line.quantity, validated_at=now, **{'delivery_line' if domain == 'sales' else 'receipt_line': line})
    obj.status = 'validated'; obj.validated_at = now; obj.save(update_fields=['status', 'validated_at', 'updated_at'])
    audit(company, user, f'inventory.{sequence}_validated', obj, after={'reference': obj.reference, 'order_id': order.pk})
    return obj
