from decimal import Decimal
from django.db.models import Sum
from rest_framework.exceptions import ValidationError
from core.administration import audit, require_module
from inventory.models import StockBalance, StockReservation


def reserve_order(company, actor, order):
    # Transaction et verrou entreprise acquis par order_action, avant tout solde.
    require_module(company.id, 'inventory')
    lines = list(order.lines.filter(document_version=order.version).exclude(product_type='service').order_by('position'))
    from inventory.fulfillment import executed_quantities
    delivered = executed_quantities(order, 'sales')
    balances = list(StockBalance.objects.select_for_update().filter(company=company, product_id__in=[line.product_id for line in lines], location__warehouse=order.warehouse, location__active=True, location__warehouse__active=True, location__type='internal').order_by('product_id', 'location_id'))
    for line in lines:
        reserved = StockReservation.objects.filter(company=company, sales_order_line=line, status='active').aggregate(total=Sum('quantity'))['total'] or Decimal(0)
        remaining = line.quantity - delivered.get(line.pk, Decimal(0)) - reserved
        for balance in balances:
            if balance.product_id != line.product_id or remaining <= 0: continue
            quantity = min(remaining, balance.quantity - balance.reserved_quantity)
            if quantity <= 0: continue
            reservation, created = StockReservation.objects.get_or_create(company=company, sales_order_line=line, product=line.product, location=balance.location, defaults={'quantity': quantity})
            if not created:
                if reservation.status not in ('active', 'fulfilled'): raise ValidationError('État de réservation incohérent.')
                reservation.quantity += quantity; reservation.status = 'active'; reservation.save(update_fields=['quantity', 'status', 'updated_at'])
            balance.reserved_quantity += quantity; balance.save(update_fields=['reserved_quantity', 'updated_at'])
            remaining -= quantity
            audit(company, actor, 'inventory.stock_reserved', reservation, after={'order_id': order.pk, 'quantity_added': quantity, 'location_id': balance.location_id})


def release_order(company, actor, order):
    require_module(company.id, 'inventory')
    reservations = list(StockReservation.objects.filter(company=company, sales_order_line__order=order, status='active').order_by('product_id', 'location_id'))
    for reservation in reservations:
        balance = StockBalance.objects.select_for_update().get(company=company, product=reservation.product, location=reservation.location)
        if balance.reserved_quantity < reservation.quantity: raise ValidationError('État de réservation incohérent.')
        balance.reserved_quantity -= reservation.quantity; balance.save(update_fields=['reserved_quantity', 'updated_at'])
        reservation.status = 'released'; reservation.save(update_fields=['status', 'updated_at'])
        audit(company, actor, 'inventory.reservation_released', reservation, after={'order_id': order.pk, 'quantity': reservation.quantity})
