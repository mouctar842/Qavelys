from decimal import Decimal, localcontext
from django.db.models import Q, Sum
from rest_framework import serializers
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView
from core.models import AuditLog, CompanyModule
from core.pagination import paginate
from core.services import permissions_for, require_membership
from core.orders import get_order
from reference.models import Partner, Product
from .models import Invoice, CreditNote
from .services import access, config, create_document, document_action, invoice_get, credit_quantities


def rows(company_id, kind):
    if kind == 'invoices': return Invoice.objects.filter(company_id=company_id).select_related('partner', 'sales_order').prefetch_related('lines')
    return CreditNote.objects.filter(company_id=company_id).select_related('invoice__partner').prefetch_related('lines__invoice_line')


def document_data(user, obj, kind, detail=True):
    _, code = config(kind)
    invoice = obj if kind == 'invoices' else obj.invoice
    permissions = permissions_for(require_membership(user, obj.company_id, f'invoicing.{code}.view'))
    result = {name: str(getattr(obj, name)) if isinstance(getattr(obj, name), Decimal) else getattr(obj, name) for name in ['id', 'reference', 'status', 'issue_date', 'currency_code', 'untaxed_amount', 'tax_amount', 'total_amount', 'validated_at', 'created_at']}
    result.update(partner_id=invoice.partner_id, partner_name=invoice.partner_snapshot.get('name', invoice.partner.name), sales_order_id=invoice.sales_order_id, order_reference=invoice.sales_order.reference if invoice.sales_order_id else None)
    if kind == 'credit-notes': result.update(invoice_id=invoice.pk, invoice_reference=invoice.reference, reason=obj.reason)
    else:
        from .payments import invoice_balance
        result['due_date'] = invoice.due_date
        result.update({key: str(value) if isinstance(value, Decimal) else value for key, value in invoice_balance(invoice).items()})
    if not detail: return result
    result['notes'] = obj.notes
    result['allowed_actions'] = [action for action in ['validate', 'cancel'] if obj.status == 'draft' and f'invoicing.{code}.{action}' in permissions]
    if kind == 'invoices':
        credited = credit_quantities(obj)
        result['issuer_snapshot'] = obj.issuer_snapshot; result['partner_snapshot'] = obj.partner_snapshot
        if 'invoicing.payment.view' in permissions:
            from .payment_views import allocation_data
            result['payment_allocations'] = [allocation_data(row) for row in obj.payment_allocations.select_related('invoice', 'payment').order_by('-created_at', '-id')]
        result['lines'] = [{**{name: str(getattr(line, name)) if isinstance(getattr(line, name), Decimal) else getattr(line, name) for name in ['id', 'product_id', 'sales_order_line_id', 'product_name', 'description', 'unit_name', 'quantity', 'unit_price', 'discount_rate', 'tax_rate', 'line_total', 'line_tax']}, 'credited_quantity': str(credited.get(line.pk, Decimal(0))), 'creditable_quantity': str(line.quantity - credited.get(line.pk, Decimal(0)))} for line in obj.lines.all().order_by('position')]
        total_credit = obj.credit_notes.filter(status='validated').aggregate(total=Sum('total_amount'))['total'] or Decimal(0)
        with localcontext() as ctx:
            ctx.prec = 60
            result['credited_amount'] = str(total_credit); result['net_amount'] = str(obj.total_amount - total_credit)
    else:
        result['lines'] = [{'id': line.pk, 'invoice_line_id': line.invoice_line_id, 'description': line.invoice_line.description, 'product_name': line.invoice_line.product_name, 'unit_name': line.invoice_line.unit_name, 'quantity': str(line.quantity), 'amount': str(line.amount)} for line in obj.lines.all()]
    return result


class DocumentList(APIView):
    def get(self, request, company_id, kind):
        access(request.user, company_id, kind)
        query = rows(company_id, kind)
        prefix = '' if kind == 'invoices' else 'invoice__'
        search = request.query_params.get('search', '').strip()[:200]
        if search: query = query.filter(Q(reference__icontains=search) | Q(**{prefix + 'partner__name__icontains': search}))
        if request.query_params.get('status'): query = query.filter(status=request.query_params['status'])
        for param, field in [('order', prefix + 'sales_order_id'), ('invoice', 'invoice_id')]:
            if request.query_params.get(param):
                if param == 'invoice' and kind == 'invoices': raise ValidationError('Filtre facture réservé aux avoirs.')
                query = query.filter(**{field: serializers.UUIDField().run_validation(request.query_params[param])})
        ordering = request.query_params.get('ordering', '-issue_date')
        if ordering not in ['issue_date', '-issue_date', 'reference', '-reference', 'total_amount', '-total_amount']: raise ValidationError('Tri invalide.')
        class Output:
            def __init__(self, items, many): self.data = [document_data(request.user, obj, kind, False) for obj in items]
        return paginate(request, query.order_by(ordering, 'id'), Output)

    def post(self, request, company_id, kind):
        obj, created = create_document(request.user, company_id, kind, request.data)
        return Response(document_data(request.user, rows(company_id, kind).get(pk=obj.pk), kind), status=201 if created else 200)


class DocumentDetail(APIView):
    def get(self, request, company_id, kind, pk):
        access(request.user, company_id, kind)
        obj = rows(company_id, kind).filter(pk=pk).first()
        if obj is None: raise NotFound()
        return Response(document_data(request.user, obj, kind))


class DocumentAction(APIView):
    def post(self, request, company_id, kind, pk, action):
        obj = document_action(request.user, company_id, kind, pk, action)
        return Response(document_data(request.user, rows(company_id, kind).get(pk=obj.pk), kind))


class Lookups(APIView):
    def get(self, request, company_id):
        access(request.user, company_id, 'invoices', 'create')
        order = None
        if request.query_params.get('order'):
            from core.administration import require_module
            require_membership(request.user, company_id, 'sales.order.view'); require_module(company_id, 'sales')
            order = get_order(company_id, 'sales', serializers.UUIDField().run_validation(request.query_params['order']))
            from core.order_views import order_data
            return Response({'order': order_data(request.user, order, 'sales')})
        search = request.query_params.get('search', '').strip()[:100]
        products = []
        if CompanyModule.objects.filter(company_id=company_id, module__code='catalog', enabled=True).exists():
            products = Product.objects.filter(company_id=company_id, active=True).filter(Q(name__icontains=search) | Q(sku__icontains=search)).select_related('unit').prefetch_related('producttax_set__tax').order_by('name')[:100]
        return Response({'partners': list(Partner.objects.filter(company_id=company_id, status='active', is_customer=True, name__icontains=search).order_by('name').values('id', 'name')[:100]), 'products': [{'id': item.pk, 'name': item.name, 'description': item.description or item.name, 'unit_price': str(item.sale_price), 'tax_rate': str(sum((link.tax.rate for link in item.producttax_set.all() if link.tax.active), Decimal(0)))} for item in products]})


class History(APIView):
    def get(self, request, company_id):
        access(request.user, company_id, 'invoices')
        obj = invoice_get(company_id, serializers.UUIDField().run_validation(request.query_params.get('invoice')))
        clause = Q(entity_type='Invoice', entity_id=obj.pk)
        permissions = permissions_for(require_membership(request.user, company_id, 'invoicing.invoice.view'))
        if 'invoicing.payment.view' in permissions: clause |= Q(entity_type='PaymentAllocation', entity_id__in=obj.payment_allocations.values('id'))
        if 'invoicing.credit_note.view' in permissions: clause |= Q(entity_type='CreditNote', entity_id__in=obj.credit_notes.values('id'))
        query = AuditLog.objects.filter(company_id=company_id).filter(clause).select_related('actor').order_by('-created_at', '-id')
        class Output:
            def __init__(self, items, many): self.data = [{'id': row.pk, 'action': row.action, 'actor': row.actor.full_name, 'created_at': row.created_at} for row in items]
        return paginate(request, query, Output)
