from django.db import transaction
from django.db.models import Q
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView
from core.administration import audit, locked_company, require_module
from core.services import require_membership
from .models import Partner, Product, ProductCategory, ProductPriceHistory, ProductTax, Tax, UnitOfMeasure
from .serializers import CategorySerializer, PartnerSerializer, ProductSerializer, TaxSerializer, UnitSerializer
from .partner_views import PrivateView

RESOURCES = {
    'partners': (Partner, PartnerSerializer, 'contacts', 'contacts'),
    'products': (Product, ProductSerializer, 'catalog', 'products'),
    'categories': (ProductCategory, CategorySerializer, 'catalog', 'categories'),
    'taxes': (Tax, TaxSerializer, 'catalog', 'taxes'),
}


def configuration(resource):
    if resource not in RESOURCES:
        raise NotFound()
    return RESOURCES[resource]


def access(user, company_id, resource, manage=False):
    model, serializer, module, permission = configuration(resource)
    member = require_membership(user, company_id, permission + ('.manage' if manage else '.view'))
    require_module(company_id, module)
    return model, serializer, member.company


def query_for(model, company_id):
    query = model.objects.filter(company_id=company_id)
    if model is Product:
        query = query.select_related('unit', 'category').prefetch_related('producttax_set__tax')
    return query


@transaction.atomic
def save(user, company_id, resource, payload, pk=None):
    model, serializer_class, module, permission = configuration(resource)
    company = locked_company(user, company_id, permission + '.manage')
    require_module(company_id, module)
    obj = query_for(model, company_id).filter(pk=pk).first() if pk else None
    if pk and obj is None:
        raise NotFound()
    before = serializer_class(obj).data if obj else {}
    serializer = serializer_class(obj, data=payload, partial=bool(pk))
    serializer.is_valid(raise_exception=True)
    data = dict(serializer.validated_data)
    tax_ids = data.pop('tax_ids', None)
    if model is ProductCategory and data.get('parent_id'):
        parent = ProductCategory.objects.filter(pk=data['parent_id'], company=company).first()
        seen = {obj.pk} if obj else set()
        while parent:
            if parent.id in seen:
                raise ValidationError({'parent_id': 'Une catégorie ne peut pas former une boucle.'})
            seen.add(parent.id)
            parent = ProductCategory.objects.filter(pk=parent.parent_id, company=company).first() if parent.parent_id else None
        if not ProductCategory.objects.filter(pk=data['parent_id'], company=company).exists():
            raise ValidationError({'parent_id': 'Catégorie parente inconnue dans cette entreprise.'})
    if model in (Tax, ProductCategory) and 'name' in data and model.objects.filter(company=company, name=data['name']).exclude(pk=pk).exists():
        raise ValidationError({'name': 'Ce nom existe déjà dans cette entreprise.'})
    if model is Product:
        if obj and (('unit_id' in data and data['unit_id'] != obj.unit_id) or ('type' in data and (data['type'] == 'service') != (obj.type == 'service'))):
            from inventory.models import StockBalance, StockMovement
            from sales.models import SalesOrderLine
            from purchases.models import PurchaseOrderLine
            used_in_order = SalesOrderLine.objects.filter(company=company, product=obj, order__confirmed_at__isnull=False).exists() or PurchaseOrderLine.objects.filter(company=company, product=obj, order__confirmed_at__isnull=False).exists()
            if used_in_order or StockBalance.objects.filter(company=company, product=obj).exists() or StockMovement.objects.filter(company=company, product=obj).exists():
                raise ValidationError('Un produit ayant un historique de stock doit conserver son unité et sa nature stock/service.')
        if 'sku' in data and Product.objects.filter(company=company, sku=data['sku']).exclude(pk=pk).exists():
            raise ValidationError({'sku': 'Ce SKU existe déjà dans cette entreprise.'})
        if data.get('category_id') and not ProductCategory.objects.filter(company=company, pk=data['category_id']).exists():
            raise ValidationError({'category_id': 'Catégorie inconnue dans cette entreprise.'})
        if 'unit_id' in data and not UnitOfMeasure.objects.filter(pk=data['unit_id']).exists():
            raise ValidationError({'unit_id': 'Unité inconnue.'})
        if tax_ids is not None and Tax.objects.filter(company=company, active=True, id__in=tax_ids).count() != len(set(tax_ids)):
            raise ValidationError({'tax_ids': 'Taxe inconnue, archivée ou appartenant à une autre entreprise.'})
    old_prices = (obj.sale_price, obj.cost_price) if model is Product and obj else None
    if obj:
        for field, value in data.items():
            setattr(obj, field, value)
        obj.save()
    else:
        obj = model.objects.create(company=company, **data)
    if model is Product:
        if tax_ids is not None:
            ProductTax.objects.filter(product=obj).exclude(tax_id__in=tax_ids).delete()
            for tax_id in set(tax_ids):
                ProductTax.objects.get_or_create(company=company, product=obj, tax_id=tax_id)
        if old_prices and old_prices != (obj.sale_price, obj.cost_price):
            ProductPriceHistory.objects.create(company=company, product=obj, actor=user, old_sale_price=old_prices[0], new_sale_price=obj.sale_price, old_cost_price=old_prices[1], new_cost_price=obj.cost_price)
    obj = query_for(model, company_id).get(pk=obj.pk)
    audit(company, user, f'{resource}.updated' if pk else f'{resource}.created', obj, before, serializer_class(obj).data)
    return obj


class ResourceList(PrivateView):
    def get(self, request, company_id, resource):
        model, serializer, _ = access(request.user, company_id, resource)
        query = query_for(model, company_id)
        search = request.query_params.get('search', '').strip()[:200]
        if search:
            term = Q(name__icontains=search)
            if model is Product:
                term |= Q(sku__icontains=search)
            elif model is Partner:
                term |= Q(email__icontains=search) | Q(phone__icontains=search)
                term |= Q(customer_reference__icontains=search) | Q(supplier_reference__icontains=search)
            query = query.filter(term)
        state = request.query_params.get('state', 'active')
        if state not in ('active', 'archived', 'all'):
            raise ValidationError('Filtre d’état invalide.')
        if state != 'all':
            if model is Partner:
                query = query.filter(status='active' if state == 'active' else 'archived')
            elif model in (Product, Tax):
                query = query.filter(active=state == 'active')
        if model is Partner:
            kind = request.query_params.get('kind')
            if kind not in (None, '', 'all', 'customer', 'supplier'): raise ValidationError('Profil de tiers invalide.')
            if kind == 'customer': query = query.filter(is_customer=True)
            elif kind == 'supplier': query = query.filter(is_supplier=True)
        try:
            page = max(1, int(request.query_params.get('page', 1)))
            size = min(100, max(1, int(request.query_params.get('page_size', 25))))
        except ValueError:
            raise ValidationError('Pagination invalide.')
        ordering = request.query_params.get('ordering', 'name')
        permitted = ['name', '-name', 'created_at', '-created_at'] + (['sku', '-sku'] if model is Product else [])
        if ordering not in permitted:
            raise ValidationError('Tri invalide.')
        query = query.order_by(ordering, 'id')
        return Response({'count': query.count(), 'page': page, 'page_size': size, 'results': serializer(query[(page - 1) * size:page * size], many=True).data})
    def post(self, request, company_id, resource):
        obj = save(request.user, company_id, resource, request.data)
        return Response(configuration(resource)[1](obj).data, status=201)


class ResourceDetail(PrivateView):
    def get(self, request, company_id, resource, pk):
        model, serializer, _ = access(request.user, company_id, resource)
        obj = query_for(model, company_id).filter(pk=pk).first()
        if obj is None:
            raise NotFound()
        return Response(serializer(obj).data)


class ResourceAction(PrivateView):
    @transaction.atomic
    def post(self, request, company_id, resource, pk, action):
        if action == 'update':
            return Response(configuration(resource)[1](save(request.user, company_id, resource, request.data, pk)).data)
        if action not in ('archive', 'restore') or resource == 'categories':
            raise NotFound()
        model, serializer, module, permission = configuration(resource)
        company = locked_company(request.user, company_id, permission + '.manage')
        require_module(company_id, module)
        obj = query_for(model, company_id).filter(pk=pk).first()
        if obj is None:
            raise NotFound()
        before = serializer(obj).data
        if model is Partner: obj.status = 'archived' if action == 'archive' else 'active'
        else: obj.active = action == 'restore'
        obj.save()
        audit(company, request.user, f'{resource}.{action}', obj, before, serializer(obj).data)
        return Response(serializer(obj).data)


class UnitsView(APIView):
    def get(self, request, company_id):
        require_membership(request.user, company_id, 'products.view')
        require_module(company_id, 'catalog')
        return Response(UnitSerializer(UnitOfMeasure.objects.order_by('category', 'name'), many=True).data)


class PriceHistoryView(APIView):
    def get(self, request, company_id, pk):
        access(request.user, company_id, 'products')
        if not Product.objects.filter(company_id=company_id, pk=pk).exists():
            raise NotFound()
        return Response([{'id': item.id, 'created_at': item.created_at, 'actor': item.actor.full_name, 'old_sale_price': str(item.old_sale_price), 'new_sale_price': str(item.new_sale_price), 'old_cost_price': str(item.old_cost_price), 'new_cost_price': str(item.new_cost_price)} for item in ProductPriceHistory.objects.filter(company_id=company_id, product_id=pk).select_related('actor').order_by('-created_at')])
