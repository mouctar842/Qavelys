import hashlib
import json
from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.db.models import Q
from rest_framework import serializers
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView
from core.administration import audit, locked_company, next_reference, require_module
from core.services import require_membership
from core.pagination import paginate
from reference.models import Product
from .models import Warehouse, StockLocation, StockBalance, StockTransfer, StockAdjustment, StockAdjustmentLine, StockMovement
from .serializers import WarehouseSerializer, LocationSerializer, BalanceSerializer, TransferSerializer, AdjustmentSerializer, MovementSerializer
from .services import internal_location, stock_product, validate_transfer, validate_adjustment

RESOURCES = {'warehouses': (Warehouse, WarehouseSerializer), 'locations': (StockLocation, LocationSerializer), 'balances': (StockBalance, BalanceSerializer), 'movements': (StockMovement, MovementSerializer), 'transfers': (StockTransfer, TransferSerializer), 'adjustments': (StockAdjustment, AdjustmentSerializer)}


def access(user, company_id, permission='inventory.view', lock=False):
    company = locked_company(user, company_id, permission) if lock else require_membership(user, company_id, permission).company
    require_module(company_id, 'inventory')
    return company


def resource_config(resource):
    if resource not in RESOURCES: raise NotFound()
    return RESOURCES[resource]


def rows(company_id, resource):
    model, _ = resource_config(resource)
    query = model.objects.filter(company_id=company_id)
    if resource == 'locations': query = query.select_related('warehouse')
    if resource == 'balances': query = query.select_related('product', 'location__warehouse')
    if resource == 'transfers': query = query.select_related('product', 'source_location__warehouse', 'destination_location__warehouse')
    if resource == 'adjustments': query = query.select_related('location').prefetch_related('lines__product')
    if resource == 'movements': query = query.select_related('product', 'source_location__warehouse', 'destination_location__warehouse', 'transfer', 'adjustment_line__adjustment', 'delivery_line__document', 'receipt_line__document')
    return query


class ResourceList(APIView):
    def get(self, request, company_id, resource):
        access(request.user, company_id)
        _, serializer = resource_config(resource)
        query = rows(company_id, resource)
        search = request.query_params.get('search', '').strip()[:200]
        if search:
            if resource in ('warehouses', 'locations'): query = query.filter(name__icontains=search)
            elif resource in ('balances', 'movements'): query = query.filter(Q(product__name__icontains=search) | Q(product__sku__icontains=search))
            else: query = query.filter(reference__icontains=search)
        if resource in ('warehouses', 'locations'):
            state = request.query_params.get('state', 'active')
            if state != 'all': query = query.filter(active=state != 'archived')
        if resource in ('transfers', 'adjustments') and request.query_params.get('status'): query = query.filter(status=request.query_params['status'])
        if resource in ('locations', 'balances') and request.query_params.get('warehouse'):
            warehouse_id = serializers.UUIDField().run_validation(request.query_params['warehouse'])
            query = query.filter(**{'warehouse_id' if resource == 'locations' else 'location__warehouse_id': warehouse_id})
        return paginate(request, query.order_by('-created_at', '-id'), serializer)

    @transaction.atomic
    def post(self, request, company_id, resource):
        model, serializer_class = resource_config(resource)
        if resource not in ('warehouses', 'locations', 'transfers', 'adjustments'): raise NotFound()
        kind = 'transfer' if resource == 'transfers' else 'adjustment'
        permission = 'inventory.warehouse.manage' if resource in ('warehouses', 'locations') else f'inventory.{kind}.create'
        company = access(request.user, company_id, permission, True)
        serializer = serializer_class(data=request.data); serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        if resource in ('warehouses', 'locations'):
            validate_structure(company_id, resource, data)
            obj = model.objects.create(company=company, **data)
            if resource == 'warehouses': StockLocation.objects.create(company=company, warehouse=obj, name='Stock')
        else:
            fingerprint = hashlib.sha256(json.dumps(data, sort_keys=True, cls=DjangoJSONEncoder).encode()).hexdigest()
            previous = model.objects.filter(company=company, request_key=data['request_key']).first()
            if previous:
                if previous.payload_hash != fingerprint: raise ValidationError('Cette clé a déjà été utilisée avec un contenu différent.')
                return Response(serializer_class(rows(company_id, resource).get(pk=previous.pk)).data)
            if resource == 'transfers':
                stock_product(company_id, data['product_id'])
                internal_location(company_id, data['source_location_id']); internal_location(company_id, data['destination_location_id'])
                if data['source_location_id'] == data['destination_location_id']: raise ValidationError('La destination doit différer de la source.')
                lines = None
            else:
                internal_location(company_id, data['location_id'])
                lines = data.pop('lines')
                ids = [line['product_id'] for line in lines]
                if len(ids) != len(set(ids)): raise ValidationError('Chaque produit doit apparaître une seule fois.')
                for product_id in ids: stock_product(company_id, product_id)
            obj = model.objects.create(company=company, created_by=request.user, reference=next_reference(company, kind), payload_hash=fingerprint, **data)
            if lines is not None: StockAdjustmentLine.objects.bulk_create([StockAdjustmentLine(company=company, adjustment=obj, **line) for line in lines])
        obj = rows(company_id, resource).get(pk=obj.pk)
        audit(company, request.user, 'inventory.' + resource + '_created', obj, after=serializer_class(obj).data)
        return Response(serializer_class(obj).data, status=201)


def validate_structure(company_id, resource, data, obj=None):
    if resource == 'warehouses':
        if 'code' in data and Warehouse.objects.filter(company_id=company_id, code=data['code']).exclude(pk=obj.pk if obj else None).exists(): raise ValidationError({'code': 'Ce code existe déjà.'})
    else:
        warehouse_id = data.get('warehouse_id', obj.warehouse_id if obj else None)
        if not Warehouse.objects.filter(company_id=company_id, pk=warehouse_id, active=True).exists(): raise ValidationError('Entrepôt actif introuvable dans cette entreprise.')
        if obj and warehouse_id != obj.warehouse_id: raise ValidationError('Un emplacement ne peut pas changer d’entrepôt.')
        if StockLocation.objects.filter(company_id=company_id, warehouse_id=warehouse_id, name=data.get('name', obj.name if obj else '')).exclude(pk=obj.pk if obj else None).exists(): raise ValidationError('Ce nom existe déjà dans cet entrepôt.')


class ResourceDetail(APIView):
    def get(self, request, company_id, resource, pk):
        access(request.user, company_id)
        _, serializer = resource_config(resource)
        obj = rows(company_id, resource).filter(pk=pk).first()
        if not obj: raise NotFound()
        return Response(serializer(obj).data)


class ResourceAction(APIView):
    @transaction.atomic
    def post(self, request, company_id, resource, pk, action):
        _, serializer_class = resource_config(resource)
        if resource not in ('warehouses', 'locations', 'transfers', 'adjustments'): raise NotFound()
        structure = resource in ('warehouses', 'locations')
        permission = 'inventory.warehouse.manage' if structure else f'inventory.{"transfer" if resource == "transfers" else "adjustment"}.{"validate" if action == "validate" else "create"}'
        company = access(request.user, company_id, permission, True)
        obj = rows(company_id, resource).filter(pk=pk).first()
        if obj is None: raise NotFound()
        if structure:
            if resource == 'locations' and obj.type != 'internal': raise ValidationError('Les emplacements logiques sont gérés par le système.')
            before = serializer_class(obj).data
            if action == 'update':
                serializer = serializer_class(obj, data=request.data, partial=True); serializer.is_valid(raise_exception=True)
                data = dict(serializer.validated_data); validate_structure(company_id, resource, data, obj)
                for field, value in data.items(): setattr(obj, field, value)
            elif action in ('archive', 'restore'):
                balances = StockBalance.objects.filter(company=company, **({'location__warehouse': obj} if resource == 'warehouses' else {'location': obj}))
                if action == 'archive' and balances.filter(Q(quantity__gt=0) | Q(reserved_quantity__gt=0)).exists(): raise ValidationError('Cet emplacement ou entrepôt contient encore du stock.')
                obj.active = action == 'restore'
            else: raise NotFound()
            obj.save()
            audit(company, request.user, 'inventory.' + resource + '_' + action, obj, before, serializer_class(obj).data)
        elif action == 'validate':
            (validate_transfer if resource == 'transfers' else validate_adjustment)(company, request.user, obj)
        elif action == 'cancel':
            if obj.status == 'validated': raise ValidationError('Un document validé doit être corrigé par un nouveau document.')
            if obj.status != 'cancelled':
                obj.status = 'cancelled'; obj.save(update_fields=['status', 'updated_at'])
                audit(company, request.user, 'inventory.document_cancelled', obj, after={'reference': obj.reference})
        else: raise NotFound()
        return Response(serializer_class(rows(company_id, resource).get(pk=obj.pk)).data)


class Lookups(APIView):
    def get(self, request, company_id):
        access(request.user, company_id)
        search = request.query_params.get('search', '').strip()[:100]
        products = Product.objects.filter(company_id=company_id, active=True).exclude(type='service').filter(Q(name__icontains=search) | Q(sku__icontains=search)).order_by('name')[:100]
        return Response({'products': [{'id': item.id, 'name': item.name, 'sku': item.sku} for item in products], 'warehouses': list(Warehouse.objects.filter(company_id=company_id, active=True).order_by('name').values('id', 'name', 'code')), 'locations': [{'id': item.id, 'name': f'{item.warehouse.code} / {item.name}'} for item in StockLocation.objects.filter(company_id=company_id, active=True, type='internal', warehouse__active=True).select_related('warehouse').order_by('warehouse__code', 'name')]})
