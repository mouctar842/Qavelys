from django.db import models
from django.utils import timezone
from reference.models import CompanyEntity

ORDER_STATUSES = [('draft', 'Brouillon'), ('pending_approval', 'En approbation'), ('confirmed', 'Confirmée'), ('completed', 'Terminée'), ('cancelled', 'Annulée')]


class OrderBase(CompanyEntity):
    partner = models.ForeignKey('reference.Partner', on_delete=models.PROTECT)
    warehouse = models.ForeignKey('inventory.Warehouse', on_delete=models.PROTECT)
    reference = models.CharField(max_length=50)
    request_key = models.UUIDField()
    payload_hash = models.CharField(max_length=64)
    status = models.CharField(max_length=24, choices=ORDER_STATUSES, default='draft')
    version = models.PositiveIntegerField(default=1)
    order_date = models.DateField(default=timezone.localdate)
    notes = models.TextField(blank=True)
    currency_code = models.CharField(max_length=3)
    untaxed_amount = models.DecimalField(max_digits=44, decimal_places=6, default=0)
    tax_amount = models.DecimalField(max_digits=44, decimal_places=6, default=0)
    total_amount = models.DecimalField(max_digits=44, decimal_places=6, default=0)
    created_by = models.ForeignKey('core.User', on_delete=models.PROTECT)
    confirmed_at = models.DateTimeField(null=True)
    completed_at = models.DateTimeField(null=True)
    closure_version = models.PositiveIntegerField(default=0, db_default=0)
    completed_by = models.ForeignKey('core.User', null=True, on_delete=models.PROTECT, related_name='%(app_label)s_completed_orders')
    class Meta:
        abstract = True
        constraints = [models.UniqueConstraint(fields=['id', 'company'], name='%(app_label)s_order_id_company_uq'), models.UniqueConstraint(fields=['company', 'reference'], name='%(app_label)s_order_reference_uq'), models.UniqueConstraint(fields=['company', 'request_key'], name='%(app_label)s_order_request_uq'), models.CheckConstraint(condition=models.Q(version__gte=1, total_amount__gte=0, untaxed_amount__gte=0, tax_amount__gte=0), name='%(app_label)s_order_amount_version_valid')]
        indexes = [models.Index(fields=['company', 'status', 'order_date'])]


class OrderLineBase(CompanyEntity):
    document_version = models.PositiveIntegerField()
    position = models.PositiveSmallIntegerField()
    product = models.ForeignKey('reference.Product', on_delete=models.PROTECT)
    product_name = models.CharField(max_length=200)
    product_type = models.CharField(max_length=20)
    unit_name = models.CharField(max_length=80)
    unit_id_snapshot = models.UUIDField()
    description = models.TextField()
    quantity = models.DecimalField(max_digits=20, decimal_places=6)
    unit_price = models.DecimalField(max_digits=20, decimal_places=6)
    discount_rate = models.DecimalField(max_digits=9, decimal_places=4, default=0)
    tax_rate = models.DecimalField(max_digits=9, decimal_places=4, default=0)
    line_total = models.DecimalField(max_digits=60, decimal_places=24)
    line_tax = models.DecimalField(max_digits=60, decimal_places=24)
    class Meta:
        abstract = True
        constraints = [models.UniqueConstraint(fields=['id', 'company'], name='%(app_label)s_line_id_company_uq'), models.UniqueConstraint(fields=['order', 'document_version', 'position'], name='%(app_label)s_line_version_position_uq'), models.CheckConstraint(condition=models.Q(quantity__gt=0, unit_price__gte=0, discount_rate__gte=0, discount_rate__lte=100, tax_rate__gte=0, tax_rate__lte=100), name='%(app_label)s_line_values_valid')]
