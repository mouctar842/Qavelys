from decimal import Decimal
from django.db import transaction
from django.db.models import Q
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.exceptions import NotFound, ValidationError
from core.administration import audit, locked_company, require_module
from core.models import Role, CompanyModule
from core.services import permissions_for, require_membership
from core.pagination import paginate
from core.order_serializers import ExactDecimalField
from .models import ApprovalRule, ApprovalRequest
from .services import decide


class RuleInput(serializers.Serializer):
    document_type = serializers.ChoiceField(choices=['sales_order', 'purchase_order'])
    min_amount = ExactDecimalField(max_digits=44, decimal_places=6, min_value=Decimal(0))
    max_amount = ExactDecimalField(max_digits=44, decimal_places=6, min_value=Decimal(0), allow_null=True)
    approver_role_id = serializers.UUIDField()
    active = serializers.BooleanField()
    version = serializers.IntegerField(min_value=1, required=False)


def rule_data(obj): return {'id': obj.pk, 'document_type': obj.document_type, 'min_amount': str(obj.min_amount), 'max_amount': str(obj.max_amount) if obj.max_amount is not None else None, 'approver_role_id': obj.approver_role_id, 'approver_role_name': obj.approver_role.name, 'active': obj.active, 'version': obj.version}


def request_data(user, obj):
    domain = 'sales' if obj.sales_order_id else 'purchases'
    order = obj.sales_order or obj.purchase_order
    member = require_membership(user, obj.company_id, f'{domain}.order.view')
    permissions = permissions_for(member)
    decision = getattr(obj, 'decision', None)
    return {'id': obj.pk, 'document_type': obj.document_type, 'document_id': order.pk, 'reference': obj.document_snapshot.get('reference', order.reference), 'document_version': obj.document_version, 'rule_version': obj.rule_version, 'total_amount': obj.document_snapshot.get('total_amount', str(order.total_amount)), 'currency_code': obj.document_snapshot.get('currency_code', order.currency_code), 'status': obj.status, 'approver_role_name': obj.rule_snapshot['role_name'], 'requested_by': obj.requested_by.user.full_name, 'created_at': obj.created_at, 'can_decide': obj.status == 'pending' and 'approvals.requests.decide' in permissions and member.membershiprole_set.filter(company_id=obj.company_id, role_id=obj.approver_role_id).exists(), 'decision': {'decision': decision.decision, 'comment': decision.comment, 'actor': decision.approver_membership.user.full_name, 'decided_at': decision.decided_at} if decision else None}


class RulesView(APIView):
    def get(self, request, company_id):
        require_membership(request.user, company_id, 'approvals.rules.view'); require_module(company_id, 'core')
        query = ApprovalRule.objects.filter(company_id=company_id).select_related('approver_role').order_by('document_type', 'min_amount', 'id')
        search = request.query_params.get('search', '').strip()[:100]
        if search: query = query.filter(approver_role__name__icontains=search)
        state = request.query_params.get('state', 'all')
        if state not in ('all', 'active', 'inactive'): raise ValidationError('État invalide.')
        if state != 'all': query = query.filter(active=state == 'active')
        class Rules:
            def __init__(self, rows, many): self.data = [rule_data(item) for item in rows]
        return paginate(request, query, Rules)
    def post(self, request, company_id): return save_rule(request, company_id)


class RuleAction(APIView):
    def post(self, request, company_id, pk): return save_rule(request, company_id, pk)


@transaction.atomic
def save_rule(request, company_id, pk=None):
    company = locked_company(request.user, company_id, 'approvals.rules.manage'); require_module(company_id, 'core')
    serializer = RuleInput(data=request.data); serializer.is_valid(raise_exception=True)
    data = dict(serializer.validated_data)
    require_module(company_id, 'sales' if data['document_type'] == 'sales_order' else 'purchases')
    if data['max_amount'] is not None and data['max_amount'] <= data['min_amount']: raise ValidationError('Le maximum doit dépasser le minimum.')
    role = Role.objects.filter(company=company, pk=data['approver_role_id']).first()
    if role is None or (data['active'] and not role.membershiprole_set.filter(membership__status='active').exists()): raise ValidationError('Rôle de cette entreprise avec au moins un membre actif requis.')
    obj = ApprovalRule.objects.filter(company=company, pk=pk).first() if pk else None
    if pk and obj is None: raise NotFound()
    if obj and data.get('version') != obj.version:
        from core.orders import Conflict
        raise Conflict()
    if data['active']:
        query = ApprovalRule.objects.filter(company=company, document_type=data['document_type'], active=True).exclude(pk=pk)
        if data['max_amount'] is not None: query = query.filter(min_amount__lt=data['max_amount'])
        if query.filter(Q(max_amount__isnull=True) | Q(max_amount__gt=data['min_amount'])).exists(): raise ValidationError('Une règle active couvre déjà une partie de cet intervalle.')
    data.pop('version', None)
    before = rule_data(obj) if obj else None
    if obj:
        for item in ApprovalRequest.objects.filter(company=company, rule=obj, status='pending').select_related('sales_order', 'purchase_order'):
            order = item.sales_order or item.purchase_order
            if order.status == 'pending_approval': order.status = 'draft'; order.save(update_fields=['status', 'updated_at'])
            item.status = 'superseded'; item.save(update_fields=['status', 'updated_at'])
        for field, value in data.items(): setattr(obj, field, value)
        obj.version += 1; obj.save()
    else: obj = ApprovalRule.objects.create(company=company, **data)
    audit(company, request.user, 'approvals.rule_updated' if pk else 'approvals.rule_created', obj, before, rule_data(obj))
    return Response(rule_data(obj), status=200 if pk else 201)


class RuleLookups(APIView):
    def get(self, request, company_id):
        require_membership(request.user, company_id, 'approvals.rules.manage'); require_module(company_id, 'core')
        roles = Role.objects.filter(company_id=company_id).order_by('name')
        return Response({'roles': [{'id': role.pk, 'name': role.name, 'has_active_members': role.membershiprole_set.filter(membership__status='active').exists()} for role in roles]})


class RequestsView(APIView):
    def get(self, request, company_id):
        member = require_membership(request.user, company_id, 'approvals.requests.view'); require_module(company_id, 'core')
        permissions = permissions_for(member)
        modules = set(CompanyModule.objects.filter(company_id=company_id, enabled=True, module__status='available').values_list('module__code', flat=True))
        kinds = [kind for domain, kind in [('sales', 'sales_order'), ('purchases', 'purchase_order')] if domain in modules and f'{domain}.order.view' in permissions]
        query = ApprovalRequest.objects.filter(company_id=company_id, document_type__in=kinds).select_related('sales_order', 'purchase_order', 'requested_by__user', 'decision__approver_membership__user')
        search = request.query_params.get('search', '').strip()[:100]
        if search: query = query.filter(Q(sales_order__reference__icontains=search) | Q(purchase_order__reference__icontains=search))
        if request.query_params.get('status'): query = query.filter(status=request.query_params['status'])
        class Requests:
            def __init__(self, rows, many): self.data = [request_data(request.user, obj) for obj in rows]
        return paginate(request, query.order_by('-created_at', '-id'), Requests)


class DecisionView(APIView):
    def post(self, request, company_id, pk):
        class DecisionInput(serializers.Serializer):
            decision = serializers.ChoiceField(choices=['approved', 'rejected'])
            comment = serializers.CharField(allow_blank=True, max_length=4000, default='')
        serializer = DecisionInput(data=request.data); serializer.is_valid(raise_exception=True)
        obj = decide(request.user, company_id, pk, **serializer.validated_data)
        return Response({'id': obj.pk, 'decision': obj.decision, 'comment': obj.comment, 'decided_at': obj.decided_at})
