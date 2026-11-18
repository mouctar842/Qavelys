from django.db.models import Q
from rest_framework import serializers
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView
from core.pagination import paginate
from core.services import require_membership, permissions_for
from core.orders import get_order
from .fulfillment import access, config, create_document, document_action
from .models import StockLocation


def rows(company_id, kind):
    model, _, _, order_field, _ = config(kind)
    return model.objects.filter(company_id=company_id).select_related(order_field, 'location__warehouse').prefetch_related('lines__order_line')


def document_data(user, obj, kind):
    _, _, _, order_field, permission = config(kind)
    order = getattr(obj, order_field)
    perms = permissions_for(require_membership(user, obj.company_id, f'inventory.{permission}.view'))
    actions = [action for action in ['validate', 'cancel'] if obj.status == 'draft' and f'inventory.{permission}.{action}' in perms and (action == 'cancel' or order.status == 'confirmed')]
    return {'id': obj.pk, 'reference': obj.reference, 'order_id': order.pk, 'order_reference': order.reference, 'order_version': obj.order_version, 'location_id': obj.location_id, 'location_name': f'{obj.location.warehouse.code} / {obj.location.name}', 'status': obj.status, 'created_at': obj.created_at, 'validated_at': obj.validated_at, 'notes': obj.notes, 'allowed_actions': actions, 'lines': [{'id': line.pk, 'order_line_id': line.order_line_id, 'product_name': line.order_line.product_name, 'product_type': line.order_line.product_type, 'unit_name': line.order_line.unit_name, 'quantity': str(line.quantity)} for line in obj.lines.all()]}


class DocumentList(APIView):
    def get(self, request, company_id, kind):
        access(request.user, company_id, kind)
        _, _, _, order_field, _ = config(kind)
        query = rows(company_id, kind)
        if request.query_params.get('order'):
            query = query.filter(**{order_field + '_id': serializers.UUIDField().run_validation(request.query_params['order'])})
        search = request.query_params.get('search', '').strip()[:200]
        if search: query = query.filter(Q(reference__icontains=search) | Q(**{order_field + '__reference__icontains': search}))
        if request.query_params.get('status'): query = query.filter(status=request.query_params['status'])
        ordering = request.query_params.get('ordering', '-created_at')
        if ordering not in ['created_at', '-created_at', 'reference', '-reference', 'validated_at', '-validated_at']: raise ValidationError('Tri invalide.')
        class Output:
            def __init__(self, items, many): self.data = [document_data(request.user, item, kind) for item in items]
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


class DocumentLookups(APIView):
    def get(self, request, company_id, kind):
        access(request.user, company_id, kind, 'create')
        _, _, domain, _, _ = config(kind)
        order = get_order(company_id, domain, serializers.UUIDField().run_validation(request.query_params.get('order')))
        locations = StockLocation.objects.filter(company_id=company_id, warehouse=order.warehouse, warehouse__active=True, active=True, type='internal').order_by('name')
        return Response({'locations': [{'id': item.pk, 'name': f'{order.warehouse.code} / {item.name}'} for item in locations]})
