from django.db import models
from reference.models import CompanyEntity


class FinancialDocument(CompanyEntity):
    reference = models.CharField(max_length=50)
    request_key = models.UUIDField()
    payload_hash = models.CharField(max_length=64)
    status = models.CharField(max_length=20, default='draft', choices=[('draft', 'Brouillon'), ('validated', 'Validé'), ('cancelled', 'Annulé')])
    currency_code = models.CharField(max_length=3)
    issue_date = models.DateField()
    notes = models.TextField(blank=True)
    untaxed_amount = models.DecimalField(max_digits=44, decimal_places=6)
    tax_amount = models.DecimalField(max_digits=44, decimal_places=6)
    total_amount = models.DecimalField(max_digits=44, decimal_places=6)
    created_by = models.ForeignKey('core.User', on_delete=models.PROTECT)
    validated_at = models.DateTimeField(null=True)
    class Meta:
        abstract = True
        constraints = [models.UniqueConstraint(fields=['id', 'company'], name='%(class)s_id_company_uq'), models.UniqueConstraint(fields=['company', 'reference'], name='%(class)s_reference_uq'), models.UniqueConstraint(fields=['company', 'request_key'], name='%(class)s_request_uq'), models.CheckConstraint(condition=models.Q(untaxed_amount__gte=0, tax_amount__gte=0, total_amount__gte=0), name='%(class)s_totals_valid')]
        indexes = [models.Index(fields=['company', 'status', 'issue_date'])]


class Invoice(FinancialDocument):
    partner = models.ForeignKey('reference.Partner', on_delete=models.PROTECT)
    sales_order = models.ForeignKey('sales.SalesOrder', on_delete=models.PROTECT, null=True, related_name='invoices')
    order_version = models.PositiveIntegerField(null=True)
    due_date = models.DateField()
    issuer_snapshot = models.JSONField(default=dict)
    partner_snapshot = models.JSONField(default=dict)
    class Meta(FinancialDocument.Meta):
        abstract = False
        constraints = FinancialDocument.Meta.constraints + [models.CheckConstraint(condition=models.Q(due_date__gte=models.F('issue_date')), name='invoice_due_date_valid')]


class InvoiceLine(CompanyEntity):
    invoice = models.ForeignKey(Invoice, related_name='lines', on_delete=models.PROTECT)
    sales_order_line = models.ForeignKey('sales.SalesOrderLine', null=True, on_delete=models.PROTECT, related_name='invoice_lines')
    product = models.ForeignKey('reference.Product', null=True, on_delete=models.PROTECT)
    position = models.PositiveSmallIntegerField()
    product_name = models.CharField(max_length=200, blank=True)
    description = models.TextField()
    unit_name = models.CharField(max_length=80, blank=True)
    quantity = models.DecimalField(max_digits=20, decimal_places=6)
    unit_price = models.DecimalField(max_digits=20, decimal_places=6)
    discount_rate = models.DecimalField(max_digits=9, decimal_places=4, default=0)
    tax_rate = models.DecimalField(max_digits=9, decimal_places=4, default=0)
    line_total = models.DecimalField(max_digits=60, decimal_places=24)
    line_tax = models.DecimalField(max_digits=60, decimal_places=24)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['id', 'company'], name='invoice_line_id_company_uq'), models.UniqueConstraint(fields=['invoice', 'position'], name='invoice_line_position_uq'), models.UniqueConstraint(fields=['invoice', 'sales_order_line'], condition=models.Q(sales_order_line__isnull=False), name='invoice_line_source_uq'), models.CheckConstraint(condition=models.Q(quantity__gt=0, unit_price__gte=0, discount_rate__gte=0, discount_rate__lte=100, tax_rate__gte=0, tax_rate__lte=100), name='invoice_line_values_valid')]


class CreditNote(FinancialDocument):
    invoice = models.ForeignKey(Invoice, related_name='credit_notes', on_delete=models.PROTECT)
    reason = models.TextField()


class CreditNoteLine(CompanyEntity):
    credit_note = models.ForeignKey(CreditNote, related_name='lines', on_delete=models.PROTECT)
    invoice_line = models.ForeignKey(InvoiceLine, related_name='credit_lines', on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=20, decimal_places=6)
    amount = models.DecimalField(max_digits=60, decimal_places=24)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['id', 'company'], name='credit_line_id_company_uq'), models.UniqueConstraint(fields=['credit_note', 'invoice_line'], name='credit_line_source_uq'), models.CheckConstraint(condition=models.Q(quantity__gt=0), name='credit_line_quantity_valid')]


class Payment(CompanyEntity):
    partner = models.ForeignKey('reference.Partner', on_delete=models.PROTECT)
    reference = models.CharField(max_length=50)
    request_key = models.UUIDField()
    payload_hash = models.CharField(max_length=64)
    amount = models.DecimalField(max_digits=44, decimal_places=6)
    currency_code = models.CharField(max_length=3)
    method = models.CharField(max_length=20, choices=[('bank_transfer', 'Virement'), ('cash', 'Espèces'), ('card', 'Carte'), ('mobile_money', 'Mobile money'), ('other', 'Autre')])
    payment_date = models.DateField()
    external_reference = models.CharField(max_length=200, blank=True)
    notes = models.TextField(blank=True)
    status = models.CharField(max_length=20, default='draft', choices=[('draft', 'Brouillon'), ('validated', 'Validé'), ('cancelled', 'Annulé')])
    partner_snapshot = models.JSONField(default=dict)
    created_by = models.ForeignKey('core.User', on_delete=models.PROTECT)
    validated_at = models.DateTimeField(null=True)
    cancellation_reason = models.TextField(blank=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['id', 'company'], name='payment_id_company_uq'), models.UniqueConstraint(fields=['company', 'reference'], name='payment_reference_uq'), models.UniqueConstraint(fields=['company', 'request_key'], name='payment_request_uq'), models.CheckConstraint(condition=models.Q(amount__gt=0), name='payment_amount_positive')]
        indexes = [models.Index(fields=['company', 'status', 'payment_date'])]


class PaymentAllocation(CompanyEntity):
    payment = models.ForeignKey(Payment, related_name='allocations', on_delete=models.PROTECT)
    invoice = models.ForeignKey(Invoice, related_name='payment_allocations', on_delete=models.PROTECT)
    amount = models.DecimalField(max_digits=44, decimal_places=6)
    request_key = models.UUIDField()
    payload_hash = models.CharField(max_length=64)
    status = models.CharField(max_length=20, default='active', choices=[('active', 'Active'), ('reversed', 'Extournée')])
    created_by = models.ForeignKey('core.User', related_name='+', on_delete=models.PROTECT)
    reversed_by = models.ForeignKey('core.User', related_name='+', on_delete=models.PROTECT, null=True)
    reversed_at = models.DateTimeField(null=True)
    reversal_reason = models.TextField(blank=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['id', 'company'], name='allocation_id_company_uq'), models.UniqueConstraint(fields=['payment', 'request_key', 'invoice'], name='allocation_batch_invoice_uq'), models.CheckConstraint(condition=models.Q(amount__gt=0), name='allocation_amount_positive'), models.CheckConstraint(condition=(models.Q(status='active', reversed_at__isnull=True, reversed_by__isnull=True) | models.Q(status='reversed', reversed_at__isnull=False, reversed_by__isnull=False)), name='allocation_reversal_valid')]
        indexes = [models.Index(fields=['company', 'invoice', 'status']), models.Index(fields=['company', 'payment', 'status'])]
