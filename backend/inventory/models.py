from django.db import models
from reference.models import CompanyEntity, Product


class Warehouse(CompanyEntity):
    name = models.CharField(max_length=160)
    code = models.CharField(max_length=30)
    active = models.BooleanField(default=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['company', 'code'], name='warehouse_company_code_unique'), models.UniqueConstraint(fields=['id', 'company'], name='warehouse_id_company_unique')]
        indexes = [models.Index(fields=['company', 'active', 'name'])]


class StockLocation(CompanyEntity):
    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, null=True, blank=True)
    name = models.CharField(max_length=160)
    type = models.CharField(max_length=20, choices=[('internal', 'Interne'), ('customer', 'Client'), ('supplier', 'Fournisseur'), ('adjustment', 'Ajustement')], default='internal')
    active = models.BooleanField(default=True)
    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['id', 'company'], name='location_id_company_unique'),
            models.UniqueConstraint(fields=['company', 'warehouse', 'name'], condition=models.Q(warehouse__isnull=False), name='location_company_warehouse_name_unique'),
            models.UniqueConstraint(fields=['company', 'type'], condition=models.Q(warehouse__isnull=True), name='location_logical_company_type_unique'),
            models.CheckConstraint(condition=(models.Q(type='internal', warehouse__isnull=False) | models.Q(type__in=['customer', 'supplier', 'adjustment'], warehouse__isnull=True)), name='location_type_warehouse_valid'),
        ]
        indexes = [models.Index(fields=['company', 'type', 'active'])]


class StockBalance(CompanyEntity):
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    location = models.ForeignKey(StockLocation, on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=20, decimal_places=6, default=0)
    reserved_quantity = models.DecimalField(max_digits=20, decimal_places=6, default=0)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['company', 'product', 'location'], name='stock_balance_company_product_location_unique'), models.CheckConstraint(condition=models.Q(quantity__gte=0, reserved_quantity__gte=0) & models.Q(quantity__gte=models.F('reserved_quantity')), name='stock_balance_nonnegative_available')]
        indexes = [models.Index(fields=['company', 'location', 'product'])]


class StockDocument(CompanyEntity):
    reference = models.CharField(max_length=50)
    request_key = models.UUIDField()
    payload_hash = models.CharField(max_length=64)
    status = models.CharField(max_length=20, default='draft', choices=[('draft', 'Brouillon'), ('validated', 'Validé'), ('cancelled', 'Annulé')])
    validated_at = models.DateTimeField(null=True)
    created_by = models.ForeignKey('core.User', on_delete=models.PROTECT)
    class Meta:
        abstract = True


class StockReservation(CompanyEntity):
    sales_order_line = models.ForeignKey('sales.SalesOrderLine', on_delete=models.PROTECT, related_name='reservations')
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    location = models.ForeignKey(StockLocation, on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=20, decimal_places=6)
    fulfilled_quantity = models.DecimalField(max_digits=20, decimal_places=6, default=0)
    status = models.CharField(max_length=20, default='active', choices=[('active', 'Active'), ('released', 'Libérée'), ('fulfilled', 'Consommée')])
    class Meta:
        constraints = [models.UniqueConstraint(fields=['sales_order_line', 'location'], name='reservation_line_location_unique'), models.CheckConstraint(condition=models.Q(quantity__gte=0, fulfilled_quantity__gte=0) & (~models.Q(status='active') | models.Q(quantity__gt=0)), name='reservation_quantity_valid')]
        indexes = [models.Index(fields=['company', 'product', 'location', 'status'])]


class StockTransfer(StockDocument):
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    source_location = models.ForeignKey(StockLocation, related_name='outgoing_transfers', on_delete=models.PROTECT)
    destination_location = models.ForeignKey(StockLocation, related_name='incoming_transfers', on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=20, decimal_places=6)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['id', 'company'], name='transfer_id_company_unique'), models.UniqueConstraint(fields=['company', 'reference'], name='transfer_company_reference_unique'), models.UniqueConstraint(fields=['company', 'request_key'], name='transfer_company_request_unique'), models.CheckConstraint(condition=models.Q(quantity__gt=0) & ~models.Q(source_location=models.F('destination_location')), name='transfer_quantity_locations_valid')]
        indexes = [models.Index(fields=['company', 'status', 'created_at'])]


class StockAdjustment(StockDocument):
    location = models.ForeignKey(StockLocation, on_delete=models.PROTECT)
    reason = models.CharField(max_length=500)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['id', 'company'], name='adjustment_id_company_unique'), models.UniqueConstraint(fields=['company', 'reference'], name='adjustment_company_reference_unique'), models.UniqueConstraint(fields=['company', 'request_key'], name='adjustment_company_request_unique')]
        indexes = [models.Index(fields=['company', 'status', 'created_at'])]


class StockAdjustmentLine(CompanyEntity):
    adjustment = models.ForeignKey(StockAdjustment, on_delete=models.PROTECT, related_name='lines')
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    counted_quantity = models.DecimalField(max_digits=20, decimal_places=6)
    difference = models.DecimalField(max_digits=20, decimal_places=6, null=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['id', 'company'], name='adjustment_line_id_company_unique'), models.UniqueConstraint(fields=['adjustment', 'product'], name='adjustment_line_product_unique'), models.CheckConstraint(condition=models.Q(counted_quantity__gte=0), name='adjustment_count_nonnegative')]


class FulfillmentDocument(StockDocument):
    location = models.ForeignKey(StockLocation, on_delete=models.PROTECT)
    order_version = models.PositiveIntegerField()
    notes = models.TextField(blank=True)
    class Meta:
        abstract = True
        constraints = [models.UniqueConstraint(fields=['id', 'company'], name='%(class)s_id_company_unique'), models.UniqueConstraint(fields=['company', 'reference'], name='%(class)s_reference_unique'), models.UniqueConstraint(fields=['company', 'request_key'], name='%(class)s_request_unique')]
        indexes = [models.Index(fields=['company', 'status', 'created_at'])]


class Delivery(FulfillmentDocument):
    sales_order = models.ForeignKey('sales.SalesOrder', on_delete=models.PROTECT, related_name='deliveries')


class GoodsReceipt(FulfillmentDocument):
    purchase_order = models.ForeignKey('purchases.PurchaseOrder', on_delete=models.PROTECT, related_name='receipts')


class FulfillmentLine(CompanyEntity):
    quantity = models.DecimalField(max_digits=20, decimal_places=6)
    class Meta:
        abstract = True
        constraints = [models.UniqueConstraint(fields=['id', 'company'], name='%(class)s_id_company_unique'), models.CheckConstraint(condition=models.Q(quantity__gt=0), name='%(class)s_quantity_positive'), models.UniqueConstraint(fields=['document', 'order_line'], name='%(class)s_source_unique')]


class DeliveryLine(FulfillmentLine):
    document = models.ForeignKey(Delivery, related_name='lines', on_delete=models.PROTECT)
    order_line = models.ForeignKey('sales.SalesOrderLine', related_name='delivery_lines', on_delete=models.PROTECT)


class GoodsReceiptLine(FulfillmentLine):
    document = models.ForeignKey(GoodsReceipt, related_name='lines', on_delete=models.PROTECT)
    order_line = models.ForeignKey('purchases.PurchaseOrderLine', related_name='receipt_lines', on_delete=models.PROTECT)


class StockMovement(CompanyEntity):
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    source_location = models.ForeignKey(StockLocation, on_delete=models.PROTECT, related_name='outgoing_movements')
    destination_location = models.ForeignKey(StockLocation, on_delete=models.PROTECT, related_name='incoming_movements')
    quantity = models.DecimalField(max_digits=20, decimal_places=6)
    validated_at = models.DateTimeField()
    transfer = models.OneToOneField(StockTransfer, on_delete=models.PROTECT, null=True)
    adjustment_line = models.OneToOneField(StockAdjustmentLine, on_delete=models.PROTECT, null=True)
    delivery_line = models.OneToOneField(DeliveryLine, on_delete=models.PROTECT, null=True)
    receipt_line = models.OneToOneField(GoodsReceiptLine, on_delete=models.PROTECT, null=True)
    class Meta:
        constraints = [models.CheckConstraint(condition=models.Q(quantity__gt=0) & ~models.Q(source_location=models.F('destination_location')), name='movement_quantity_locations_valid'), models.CheckConstraint(condition=(models.Q(transfer__isnull=False, adjustment_line__isnull=True, delivery_line__isnull=True, receipt_line__isnull=True) | models.Q(transfer__isnull=True, adjustment_line__isnull=False, delivery_line__isnull=True, receipt_line__isnull=True) | models.Q(transfer__isnull=True, adjustment_line__isnull=True, delivery_line__isnull=False, receipt_line__isnull=True) | models.Q(transfer__isnull=True, adjustment_line__isnull=True, delivery_line__isnull=True, receipt_line__isnull=False)), name='movement_exactly_one_source')]
        indexes = [models.Index(fields=['company', 'product', 'validated_at'])]
