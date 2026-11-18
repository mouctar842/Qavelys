from decimal import Decimal
from django.db.models import Q, Sum
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.exceptions import ValidationError
from core.models import AuditLog
from core.services import require_membership, permissions_for
from core.pagination import paginate
from core.order_serializers import VersionInput, line_data
from core.orders import access, models_for, query_orders, get_order, current_lines, save_order, order_action


def order_summary(obj):
    return {'id': obj.pk, 'reference': obj.reference, 'status': obj.status, 'version': obj.version, 'partner_id': obj.partner_id, 'partner_name': obj.partner.name, 'warehouse_id': obj.warehouse_id, 'warehouse_name': obj.warehouse.name, 'order_date': obj.order_date, 'currency_code': obj.currency_code, 'untaxed_amount': str(obj.untaxed_amount), 'tax_amount': str(obj.tax_amount), 'total_amount': str(obj.total_amount), 'created_at': obj.created_at, 'completed_at': obj.completed_at}


def order_data(user, obj, domain):
    from approvals.services import approval_state
    from approvals.views import request_data
    from inventory.models import StockReservation
    from inventory.fulfillment import executed_quantities, has_validated_effects
    from invoicing.services import billed_quantities
    result = order_summary(obj)
    result['closure_version'] = obj.closure_version
    rule, approved = approval_state(obj, domain)
    member = require_membership(user, obj.company_id, f'{domain}.order.view')
    permissions = permissions_for(member)
    actions = []
    if obj.status == 'draft': actions.extend(['edit', 'cancel'])
    if obj.status == 'pending_approval': actions.extend(['reopen', 'cancel'])
    if obj.status in ('draft', 'pending_approval'):
        if approved: actions.append('confirm')
        else: actions.append('submit')
    if obj.status == 'confirmed':
        if not has_validated_effects(obj, domain) and not (domain == 'sales' and obj.invoices.filter(status='validated').exists()): actions.append('cancel')
        if domain == 'sales': actions.append('reserve')
    if obj.status in ('confirmed', 'completed'):
        from .completion import completion_state
        from rest_framework.exceptions import PermissionDenied
        try: result['completion'] = completion_state(user, obj, domain)
        except PermissionDenied: result['completion'] = None
        if obj.status == 'confirmed' and result['completion'] and result['completion']['eligible']: actions.append('complete')
        if obj.status == 'completed': actions.append('resume')
    result['allowed_actions'] = [action for action in actions if f'{domain}.order.{"edit" if action == "reopen" else action}' in permissions]
    result['approval'] = {'required': rule is not None, 'approved': approved, 'approver_role_name': rule.approver_role.name if rule else None}
    result['notes'] = obj.notes
    result['lead_id'] = obj.lead_id if domain == 'sales' else None
    lines = current_lines(obj)
    executed = executed_quantities(obj, domain)
    billed = billed_quantities(obj) if domain == 'sales' else {}
    if domain == 'sales': result['invoicing_status'] = 'done' if lines and all(billed.get(line.pk, Decimal(0)) >= line.quantity for line in lines) else 'partial' if any(billed.values()) else 'not_started'
    result['fulfillment_status'] = 'done' if lines and all(executed.get(line.pk, Decimal(0)) >= line.quantity for line in lines) else 'partial' if executed else 'not_started'
    reservations = list(StockReservation.objects.filter(company=obj.company, sales_order_line__order_id=obj.pk).select_related('location__warehouse').order_by('created_at')) if domain == 'sales' else []
    totals = {}
    for reservation in reservations:
        if reservation.status == 'active': totals[reservation.sales_order_line_id] = totals.get(reservation.sales_order_line_id, Decimal(0)) + reservation.quantity
    result['lines'] = []
    for line in lines:
        data = line_data(line)
        fulfilled = executed.get(line.pk, Decimal(0))
        data.update({'fulfilled_quantity': str(fulfilled), 'remaining_quantity': str(line.quantity - fulfilled)})
        if domain == 'sales': data.update({'billed_quantity': str(billed.get(line.pk, Decimal(0))), 'billable_quantity': str(line.quantity - billed.get(line.pk, Decimal(0)))})
        if domain == 'sales':
            reserved = totals.get(line.pk, Decimal(0))
            data.update({'reserved_quantity': str(reserved), 'waiting_quantity': str(max(Decimal(0), line.quantity - fulfilled - reserved) if obj.status == 'confirmed' and line.product_type != 'service' else Decimal(0))})
        result['lines'].append(data)
    result['reservations'] = [{'id': item.pk, 'line_id': item.sales_order_line_id, 'location': f'{item.location.warehouse.code} / {item.location.name}', 'quantity': str(item.quantity), 'fulfilled_quantity': str(item.fulfilled_quantity), 'status': item.status} for item in reservations]
    result['approval_requests'] = [request_data(user, item) for item in obj.approval_requests.select_related('approver_role', 'requested_by__user', 'sales_order', 'purchase_order', 'decision__approver_membership__user').order_by('-created_at')]
    return result


class OrdersView(APIView):
    def get(self, request, company_id, domain):
        access(request.user, company_id, domain)
        query = query_orders(company_id, domain)
        search = request.query_params.get('search', '').strip()[:200]
        if search: query = query.filter(Q(reference__icontains=search) | Q(partner__name__icontains=search))
        status = request.query_params.get('status', '')
        if status: query = query.filter(status=status)
        if request.query_params.get('lead'):
            from rest_framework import serializers
            if domain != 'sales': raise ValidationError('Filtre prospect réservé aux ventes.')
            query = query.filter(lead_id=serializers.UUIDField().run_validation(request.query_params['lead']))
        ordering = request.query_params.get('ordering', '-order_date')
        if ordering not in ['order_date', '-order_date', 'reference', '-reference', 'total_amount', '-total_amount', 'partner__name', '-partner__name']: raise ValidationError('Tri invalide.')
        class Summary:
            def __init__(self, rows, many): self.data = [order_summary(obj) for obj in rows]
        return paginate(request, query.order_by(ordering, 'id'), Summary)

    def post(self, request, company_id, domain):
        obj, created = save_order(request.user, company_id, domain, request.data)
        return Response(order_data(request.user, get_order(company_id, domain, obj.pk), domain), status=201 if created else 200)


class OrderDetail(APIView):
    def get(self, request, company_id, domain, pk):
        access(request.user, company_id, domain)
        return Response(order_data(request.user, get_order(company_id, domain, pk), domain))


class OrderAction(APIView):
    def post(self, request, company_id, domain, pk, action):
        if action == 'update': obj, _ = save_order(request.user, company_id, domain, request.data, pk)
        else:
            serializer = VersionInput(data=request.data); serializer.is_valid(raise_exception=True)
            from rest_framework import serializers
            reason = serializers.CharField(min_length=8, max_length=1000).run_validation(request.data.get('reason', '')) if action == 'resume' else ''
            closure_version = serializers.IntegerField(min_value=0).run_validation(request.data.get('closure_version', serializers.empty)) if action in ('complete', 'resume') else None
            obj = order_action(request.user, company_id, domain, pk, action, serializer.validated_data['version'], reason, closure_version)
        return Response(order_data(request.user, get_order(company_id, domain, obj.pk), domain))


class OrderLookups(APIView):
    def get(self, request, company_id, domain):
        from reference.models import Partner, Product
        from inventory.models import Warehouse
        access(request.user, company_id, domain)
        search = request.query_params.get('search', '').strip()[:100]
        products = Product.objects.filter(company_id=company_id, active=True).filter(Q(name__icontains=search) | Q(sku__icontains=search)).select_related('unit').prefetch_related('producttax_set__tax').order_by('name')[:100]
        partners = Partner.objects.filter(company_id=company_id, status='active', **{'is_customer' if domain == 'sales' else 'is_supplier': True}).filter(name__icontains=search).order_by('name')[:100]
        return Response({'products': [{'id': product.pk, 'name': product.name, 'description': product.description, 'sku': product.sku, 'unit_name': product.unit.name, 'type': product.type, 'unit_price': str(product.sale_price if domain == 'sales' else product.cost_price), 'tax_rate': str(sum((link.tax.rate for link in product.producttax_set.all() if link.tax.active), Decimal(0)))} for product in products], 'partners': list(partners.values('id', 'name')), 'warehouses': list(Warehouse.objects.filter(company_id=company_id, active=True).order_by('name').values('id', 'name', 'code'))})


class OrderHistory(APIView):
    def get(self, request, company_id, domain, pk):
        access(request.user, company_id, domain)
        obj = get_order(company_id, domain, pk)
        clause = Q(entity_type=obj.__class__.__name__, entity_id=obj.pk) | Q(entity_type='ApprovalRequest', entity_id__in=obj.approval_requests.values('id'))
        documents = obj.deliveries if domain == 'sales' else obj.receipts
        clause |= Q(entity_type='Delivery' if domain == 'sales' else 'GoodsReceipt', entity_id__in=documents.values('id'))
        if domain == 'sales':
            from inventory.models import StockReservation
            clause |= Q(entity_type='StockReservation', entity_id__in=StockReservation.objects.filter(company_id=company_id, sales_order_line__order=obj).values('id'))
        query = AuditLog.objects.filter(company_id=company_id).filter(clause).select_related('actor').order_by('-created_at', '-id')
        class History:
            def __init__(self, rows, many): self.data = [{'id': item.pk, 'action': item.action, 'actor': item.actor.full_name, 'created_at': item.created_at, 'before_data': item.before_data, 'after_data': item.after_data} for item in rows]
        return paginate(request, query, History)
