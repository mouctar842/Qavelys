from decimal import Decimal
from django.db.models import Q
from rest_framework import serializers
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView
from core.models import AuditLog
from core.pagination import paginate
from core.services import require_membership, permissions_for
from reference.models import Partner
from .models import Invoice
from .payments import access, allocated_amount, available_amount, invoice_balance, create_payment, payment_action, allocate, reverse_allocation, get_payment


def allocation_data(row):
    return {'id': row.pk, 'invoice_id': row.invoice_id, 'invoice_reference': row.invoice.reference, 'payment_id': row.payment_id, 'payment_reference': row.payment.reference, 'amount': str(row.amount), 'status': row.status, 'created_at': row.created_at, 'reversed_at': row.reversed_at, 'reversal_reason': row.reversal_reason}


def payment_data(user, obj, detail=True):
    result = {name: str(getattr(obj, name)) if isinstance(getattr(obj, name), Decimal) else getattr(obj, name) for name in ['id', 'reference', 'status', 'amount', 'currency_code', 'method', 'payment_date', 'external_reference', 'validated_at', 'created_at']}
    result.update(partner_id=obj.partner_id, partner_name=obj.partner_snapshot.get('name', obj.partner.name), allocated_amount=str(allocated_amount(obj)), available_amount=str(available_amount(obj)))
    if not detail: return result
    permissions = permissions_for(require_membership(user, obj.company_id, 'invoicing.payment.view'))
    result['can_view_invoices'] = 'invoicing.invoice.view' in permissions
    result['allocations'] = [allocation_data(row) for row in obj.allocations.select_related('invoice', 'payment').order_by('-created_at', '-id')] if result['can_view_invoices'] else []
    actions = []
    if obj.status == 'draft': actions.extend(['validate', 'cancel'])
    if obj.status == 'validated':
        if allocated_amount(obj) == 0: actions.append('cancel')
        if available_amount(obj) > 0 and result['can_view_invoices']: actions.append('allocate')
    result['allowed_actions'] = [verb for verb in actions if f'invoicing.payment.{verb}' in permissions]
    result['can_reverse'] = result['can_view_invoices'] and 'invoicing.payment.reverse_allocation' in permissions
    result['notes'] = obj.notes; result['cancellation_reason'] = obj.cancellation_reason
    return result


class Payments(APIView):
    def get(self, request, company_id):
        from .models import Payment
        access(request.user, company_id)
        query = Payment.objects.filter(company_id=company_id).select_related('partner')
        search = request.query_params.get('search', '').strip()[:200]
        if search: query = query.filter(Q(reference__icontains=search) | Q(partner__name__icontains=search) | Q(external_reference__icontains=search))
        if request.query_params.get('status'): query = query.filter(status=request.query_params['status'])
        if request.query_params.get('partner'): query = query.filter(partner_id=serializers.UUIDField().run_validation(request.query_params['partner']))
        ordering = request.query_params.get('ordering', '-payment_date')
        if ordering not in ['payment_date', '-payment_date', 'reference', '-reference', 'amount', '-amount']: raise ValidationError('Tri invalide.')
        class Output:
            def __init__(self, items, many): self.data = [payment_data(request.user, row, False) for row in items]
        return paginate(request, query.order_by(ordering, 'id'), Output)

    def post(self, request, company_id):
        obj, created = create_payment(request.user, company_id, request.data)
        return Response(payment_data(request.user, get_payment(company_id, obj.pk)), status=201 if created else 200)


class Detail(APIView):
    def get(self, request, company_id, pk):
        access(request.user, company_id)
        return Response(payment_data(request.user, get_payment(company_id, pk)))


class Action(APIView):
    def post(self, request, company_id, pk, action):
        if action == 'allocate': obj, _, _ = allocate(request.user, company_id, pk, request.data)
        else: obj = payment_action(request.user, company_id, pk, action, request.data)
        return Response(payment_data(request.user, get_payment(company_id, obj.pk)))


class Reverse(APIView):
    def post(self, request, company_id, pk):
        obj = reverse_allocation(request.user, company_id, pk, request.data)
        return Response(payment_data(request.user, get_payment(company_id, obj.payment_id)))


class Lookups(APIView):
    def get(self, request, company_id):
        access(request.user, company_id, 'create')
        search = request.query_params.get('search', '').strip()[:100]
        return Response({'partners': list(Partner.objects.filter(company_id=company_id, status='active', is_customer=True, name__icontains=search).order_by('name').values('id', 'name')[:100])})


class PaymentInvoices(APIView):
    def get(self, request, company_id, pk):
        access(request.user, company_id, 'allocate')
        obj = get_payment(company_id, pk)
        search = request.query_params.get('search', '').strip()[:100]
        query = Invoice.objects.filter(company_id=company_id, partner_id=obj.partner_id, currency_code=obj.currency_code, status='validated', reference__icontains=search).order_by('due_date', 'id')
        class Output:
            def __init__(self, items, many): self.data = [{'id': row.pk, 'reference': row.reference, 'due_date': row.due_date, 'currency_code': row.currency_code, **{key: str(value) if isinstance(value, Decimal) else value for key, value in invoice_balance(row).items()}} for row in items]
        return paginate(request, query, Output)


class History(APIView):
    def get(self, request, company_id, pk):
        access(request.user, company_id)
        obj = get_payment(company_id, pk)
        clause = Q(entity_type='Payment', entity_id=obj.pk) | Q(entity_type='PaymentAllocation', entity_id__in=obj.allocations.values('id'))
        query = AuditLog.objects.filter(company_id=company_id).filter(clause).select_related('actor').order_by('-created_at', '-id')
        class Output:
            def __init__(self, items, many): self.data = [{'id': row.pk, 'action': row.action, 'actor': row.actor.full_name, 'created_at': row.created_at} for row in items]
        return paginate(request, query, Output)
