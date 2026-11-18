from django.db import models
from reference.models import CompanyEntity

DOCUMENT_TYPES = [('sales_order', 'Vente'), ('purchase_order', 'Achat')]


class ApprovalRule(CompanyEntity):
    document_type = models.CharField(max_length=30, choices=DOCUMENT_TYPES)
    min_amount = models.DecimalField(max_digits=44, decimal_places=6, default=0)
    max_amount = models.DecimalField(max_digits=44, decimal_places=6, null=True, blank=True)
    approver_role = models.ForeignKey('core.Role', on_delete=models.PROTECT)
    active = models.BooleanField(default=True)
    version = models.PositiveIntegerField(default=1)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['id', 'company'], name='approval_rule_id_company_uq'), models.CheckConstraint(condition=models.Q(min_amount__gte=0) & (models.Q(max_amount__isnull=True) | models.Q(max_amount__gt=models.F('min_amount'))), name='approval_rule_interval_valid')]
        indexes = [models.Index(fields=['company', 'document_type', 'active'])]


class ApprovalRequest(CompanyEntity):
    rule = models.ForeignKey(ApprovalRule, on_delete=models.PROTECT)
    approver_role = models.ForeignKey('core.Role', on_delete=models.PROTECT)
    rule_version = models.PositiveIntegerField()
    rule_snapshot = models.JSONField()
    document_snapshot = models.JSONField(default=dict)
    document_type = models.CharField(max_length=30, choices=DOCUMENT_TYPES)
    sales_order = models.ForeignKey('sales.SalesOrder', on_delete=models.PROTECT, null=True, related_name='approval_requests')
    purchase_order = models.ForeignKey('purchases.PurchaseOrder', on_delete=models.PROTECT, null=True, related_name='approval_requests')
    document_version = models.PositiveIntegerField()
    requested_by = models.ForeignKey('core.Membership', on_delete=models.PROTECT)
    status = models.CharField(max_length=24, default='pending', choices=[('pending', 'En attente'), ('approved', 'Approuvée'), ('rejected', 'Rejetée'), ('superseded', 'Obsolète')])
    class Meta:
        constraints = [models.UniqueConstraint(fields=['id', 'company'], name='approval_request_id_company_uq'), models.CheckConstraint(condition=(models.Q(document_type='sales_order', sales_order__isnull=False, purchase_order__isnull=True) | models.Q(document_type='purchase_order', purchase_order__isnull=False, sales_order__isnull=True)), name='approval_request_source_valid'), models.UniqueConstraint(fields=['sales_order'], condition=models.Q(status='pending'), name='approval_pending_sale_unique'), models.UniqueConstraint(fields=['purchase_order'], condition=models.Q(status='pending'), name='approval_pending_purchase_unique')]
        indexes = [models.Index(fields=['company', 'status', 'created_at'])]


class ApprovalDecision(CompanyEntity):
    request = models.OneToOneField(ApprovalRequest, on_delete=models.PROTECT, related_name='decision')
    approver_membership = models.ForeignKey('core.Membership', on_delete=models.PROTECT)
    decision = models.CharField(max_length=16, choices=[('approved', 'Approuvée'), ('rejected', 'Rejetée')])
    comment = models.TextField(blank=True)
    decided_at = models.DateTimeField(auto_now_add=True)
