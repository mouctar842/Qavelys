from django.db import transaction
from django.db.models import Q
from rest_framework.exceptions import PermissionDenied, ValidationError
from core.administration import audit, locked_company, require_module
from core.services import require_membership
from .models import ApprovalRule, ApprovalRequest, ApprovalDecision


def order_filter(obj, domain): return {'sales_order' if domain == 'sales' else 'purchase_order': obj}


def invalidate_requests(obj, domain, pending_only=False):
    statuses = ['pending'] if pending_only else ['pending', 'approved']
    ApprovalRequest.objects.filter(company=obj.company, **order_filter(obj, domain), status__in=statuses).update(status='superseded')


def approval_state(obj, domain):
    kind = 'sales_order' if domain == 'sales' else 'purchase_order'
    matches = ApprovalRule.objects.filter(company=obj.company, document_type=kind, active=True, min_amount__lte=obj.total_amount).filter(Q(max_amount__isnull=True) | Q(max_amount__gt=obj.total_amount))
    rules = list(matches[:2])
    if len(rules) > 1: raise ValidationError('Règles d’approbation contradictoires : contactez votre administrateur.')
    rule = rules[0] if rules else None
    approved = rule is None or ApprovalRequest.objects.filter(company=obj.company, **order_filter(obj, domain), rule=rule, rule_version=rule.version, document_version=obj.version, status='approved').exists()
    return rule, approved


def submit_request(user, obj, domain, rule):
    previous = ApprovalRequest.objects.filter(company=obj.company, **order_filter(obj, domain), status='pending').first()
    if previous and previous.document_version == obj.version and previous.rule_id == rule.pk and previous.rule_version == rule.version:
        return previous
    invalidate_requests(obj, domain, pending_only=True)
    member = require_membership(user, obj.company_id, f'{domain}.order.submit')
    if not rule.approver_role.membershiprole_set.filter(membership__status='active').exists(): raise ValidationError('Le rôle approbateur ne possède aucun membre actif.')
    request = ApprovalRequest.objects.create(company=obj.company, rule=rule, approver_role=rule.approver_role, rule_version=rule.version, rule_snapshot={'min_amount': str(rule.min_amount), 'max_amount': str(rule.max_amount) if rule.max_amount is not None else None, 'role_name': rule.approver_role.name}, document_snapshot={'reference': obj.reference, 'total_amount': str(obj.total_amount), 'currency_code': obj.currency_code, 'partner_name': obj.partner.name, 'order_date': obj.order_date.isoformat()}, document_type=rule.document_type, document_version=obj.version, requested_by=member, **order_filter(obj, domain))
    obj.status = 'pending_approval'; obj.save(update_fields=['status', 'updated_at'])
    audit(obj.company, user, 'approvals.request_submitted', request, after={'document_id': obj.pk, 'document_version': obj.version, 'rule_version': rule.version})
    return request


@transaction.atomic
def decide(user, company_id, pk, decision, comment):
    company = locked_company(user, company_id, 'approvals.requests.decide')
    request = ApprovalRequest.objects.select_related('sales_order', 'purchase_order', 'rule').filter(company=company, pk=pk).first()
    if request is None:
        from rest_framework.exceptions import NotFound
        raise NotFound()
    domain = 'sales' if request.sales_order_id else 'purchases'
    require_module(company_id, domain)
    member = require_membership(user, company_id, f'{domain}.order.view')
    if not member.membershiprole_set.filter(company=company, role_id=request.approver_role_id).exists(): raise PermissionDenied('Votre rôle ne permet pas de décider cette demande.')
    previous = ApprovalDecision.objects.filter(request=request).first()
    if previous:
        if previous.decision != decision: raise ValidationError('Une décision contraire est déjà enregistrée.')
        return previous
    obj = request.sales_order or request.purchase_order
    rule, _ = approval_state(obj, domain)
    if request.status != 'pending' or obj.status != 'pending_approval' or obj.version != request.document_version or rule is None or rule.pk != request.rule_id or rule.version != request.rule_version:
        raise ValidationError('Cette demande n’est plus applicable. Rechargez le document.')
    result = ApprovalDecision.objects.create(company=company, request=request, approver_membership=member, decision=decision, comment=comment)
    request.status = decision; request.save(update_fields=['status', 'updated_at'])
    obj.status = 'draft'; obj.save(update_fields=['status', 'updated_at'])
    audit(company, user, 'approvals.' + decision, request, after={'document_id': obj.pk, 'version': obj.version, 'comment': comment})
    return result
