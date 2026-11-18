from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from core.administration import audit, locked_company, require_module
from reference.models import Product
from .models import Warehouse, StockLocation, StockBalance, StockMovement


def initialize_inventory(company):
    warehouse, _ = Warehouse.objects.get_or_create(company=company, code='MAIN', defaults={'name': 'Entrepôt principal'})
    StockLocation.objects.get_or_create(company=company, warehouse=warehouse, name='Stock', defaults={'type': 'internal'})
    for kind, name in [('customer', 'Clients'), ('supplier', 'Fournisseurs'), ('adjustment', 'Ajustements')]:
        StockLocation.objects.get_or_create(company=company, warehouse=None, type=kind, defaults={'name': name})


def internal_location(company_id, pk):
    location = StockLocation.objects.filter(company_id=company_id, pk=pk, type='internal', active=True, warehouse__active=True).first()
    if not location: raise ValidationError('Emplacement interne actif introuvable dans cette entreprise.')
    return location


def stock_product(company_id, pk):
    product = Product.objects.filter(company_id=company_id, pk=pk, active=True).exclude(type='service').first()
    if not product: raise ValidationError('Produit actif géré en stock introuvable dans cette entreprise.')
    return product


def locked_balances(company, pairs):
    # Appelé après le verrou entreprise commun à toutes les opérations métier.
    for product_id, location_id in sorted(set(pairs), key=lambda item: (str(item[0]), str(item[1]))):
        StockBalance.objects.get_or_create(company=company, product_id=product_id, location_id=location_id)
    query = StockBalance.objects.select_for_update().filter(company=company, product_id__in=[item[0] for item in pairs], location_id__in=[item[1] for item in pairs]).order_by('product_id', 'location_id')
    return {(item.product_id, item.location_id): item for item in query}


@transaction.atomic
def validate_transfer(company, actor, obj):
    company = locked_company(actor, company.id, 'inventory.transfer.validate')
    require_module(company.id, 'inventory')
    if obj.company_id != company.pk: raise ValidationError('Transfert extérieur à cette entreprise.')
    obj.refresh_from_db()
    if obj.status == 'validated': return obj
    if obj.status != 'draft': raise ValidationError('Ce transfert ne peut plus être validé.')
    stock_product(company.id, obj.product_id)
    internal_location(company.id, obj.source_location_id); internal_location(company.id, obj.destination_location_id)
    balances = locked_balances(company, [(obj.product_id, obj.source_location_id), (obj.product_id, obj.destination_location_id)])
    source = balances[(obj.product_id, obj.source_location_id)]; destination = balances[(obj.product_id, obj.destination_location_id)]
    if source.quantity - source.reserved_quantity < obj.quantity: raise ValidationError('Stock disponible insuffisant.')
    if destination.quantity + obj.quantity >= Decimal('100000000000000'): raise ValidationError('Quantité maximale dépassée.')
    source.quantity -= obj.quantity; destination.quantity += obj.quantity
    source.save(update_fields=['quantity', 'updated_at']); destination.save(update_fields=['quantity', 'updated_at'])
    obj.status = 'validated'; obj.validated_at = timezone.now(); obj.save(update_fields=['status', 'validated_at', 'updated_at'])
    StockMovement.objects.create(company=company, product=obj.product, source_location=obj.source_location, destination_location=obj.destination_location, quantity=obj.quantity, transfer=obj, validated_at=obj.validated_at)
    audit(company, actor, 'inventory.transfer_validated', obj, after={'reference': obj.reference, 'quantity': obj.quantity})
    return obj


@transaction.atomic
def validate_adjustment(company, actor, obj):
    company = locked_company(actor, company.id, 'inventory.adjustment.validate')
    require_module(company.id, 'inventory')
    if obj.company_id != company.pk: raise ValidationError('Ajustement extérieur à cette entreprise.')
    obj.refresh_from_db()
    if obj.status == 'validated': return obj
    if obj.status != 'draft': raise ValidationError('Cet ajustement ne peut plus être validé.')
    internal_location(company.id, obj.location_id)
    lines = list(obj.lines.order_by('product_id'))
    for line in lines: stock_product(company.id, line.product_id)
    balances = locked_balances(company, [(line.product_id, obj.location_id) for line in lines])
    logical = StockLocation.objects.get(company=company, type='adjustment', warehouse=None)
    now = timezone.now()
    for line in lines:
        balance = balances[(line.product_id, obj.location_id)]
        if line.counted_quantity < balance.reserved_quantity: raise ValidationError('Le comptage est inférieur au stock réservé.')
        line.difference = line.counted_quantity - balance.quantity
        line.save(update_fields=['difference', 'updated_at'])
        if line.difference:
            StockMovement.objects.create(company=company, product=line.product, source_location=logical if line.difference > 0 else obj.location, destination_location=obj.location if line.difference > 0 else logical, quantity=abs(line.difference), adjustment_line=line, validated_at=now)
        balance.quantity = line.counted_quantity; balance.save(update_fields=['quantity', 'updated_at'])
    obj.status = 'validated'; obj.validated_at = now; obj.save(update_fields=['status', 'validated_at', 'updated_at'])
    audit(company, actor, 'inventory.adjustment_validated', obj, after={'reference': obj.reference, 'reason': obj.reason})
    return obj
