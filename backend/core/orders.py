import hashlib
import json
from decimal import Decimal
from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.db.models import Prefetch
from django.utils import timezone
from rest_framework.exceptions import APIException, NotFound, PermissionDenied, ValidationError
from core.administration import audit, locked_company, next_reference, require_module
from core.money import document_totals, exact_line
from core.services import require_membership
from reference.models import Partner, Product
from inventory.models import StockLocation, Warehouse
from .order_serializers import OrderInput


class Conflict(APIException):
    status_code = 409
    default_detail = 'Le document a changé. Rechargez sa dernière version.'


def models_for(domain):
    if domain == 'sales':
        from sales.models import SalesOrder, SalesOrderLine
        return SalesOrder, SalesOrderLine, 'sales_order'
    if domain == 'purchases':
        from purchases.models import PurchaseOrder, PurchaseOrderLine
        return PurchaseOrder, PurchaseOrderLine, 'purchase_order'
    raise NotFound()


def access(user, company_id, domain, action='view', lock=False):
    models_for(domain)
    permission = f'{domain}.order.{action}'
    company = locked_company(user, company_id, permission) if lock else require_membership(user, company_id, permission).company
    if action != 'view': require_membership(user, company_id, f'{domain}.order.view')
    require_module(company_id, domain)
    return company


def query_orders(company_id, domain):
    model, _, _ = models_for(domain)
    query = model.objects.filter(company_id=company_id).select_related('partner', 'warehouse', 'created_by')
    return query.select_related('lead') if domain == 'sales' else query


def get_order(company_id, domain, pk):
    obj = query_orders(company_id, domain).filter(pk=pk).first()
    if obj is None: raise NotFound()
    return obj


def check_version(obj, version):
    if obj.version != version: raise Conflict()


def current_lines(obj):
    return list(obj.lines.filter(document_version=obj.version).select_related('product').order_by('position'))


def checked_relations(user, company, domain, data):
    partner = Partner.objects.filter(company=company, pk=data['partner_id'], status='active', **{'is_customer' if domain == 'sales' else 'is_supplier': True}).first()
    if partner is None: raise ValidationError({'partner_id': 'Client ou fournisseur actif introuvable dans cette entreprise.'})
    if not Warehouse.objects.filter(company=company, pk=data['warehouse_id'], active=True).exists(): raise ValidationError({'warehouse_id': 'Entrepôt actif introuvable dans cette entreprise.'})
    lead = None
    if domain == 'purchases' and data.get('lead_id'): raise ValidationError('Un achat ne peut pas être issu d’un prospect.')
    if domain == 'sales' and data.get('lead_id'):
        from crm.models import Lead
        require_membership(user, company.id, 'crm.manage'); require_module(company.id, 'crm')
        lead = Lead.objects.filter(company=company, pk=data['lead_id']).first()
        if lead is None: raise ValidationError({'lead_id': 'Prospect introuvable dans cette entreprise.'})
        if lead.partner_id and lead.partner_id != partner.pk: raise ValidationError('Le devis doit utiliser le client rattaché au prospect.')
    return partner, lead


def prepare_lines(company, domain, inputs):
    products = {obj.id: obj for obj in Product.objects.filter(company=company, active=True, id__in=[item['product_id'] for item in inputs]).select_related('unit').prefetch_related('producttax_set__tax')}
    result = []
    for position, data in enumerate(inputs, 1):
        product = products.get(data['product_id'])
        if product is None: raise ValidationError({'lines': f'Produit de ligne {position} inactif ou extérieur à cette entreprise.'})
        tax = data.get('tax_rate', sum((link.tax.rate for link in product.producttax_set.all() if link.tax.active), Decimal(0)))
        price = data.get('unit_price', product.sale_price if domain == 'sales' else product.cost_price)
        net, amount_tax = exact_line(data['quantity'], price, data['discount_rate'], tax)
        result.append({'position': position, 'product': product, 'product_name': product.name, 'product_type': product.type, 'unit_name': product.unit.name, 'unit_id_snapshot': product.unit_id, 'description': data.get('description') or product.description or product.name, 'quantity': data['quantity'], 'unit_price': price, 'discount_rate': data['discount_rate'], 'tax_rate': tax, 'line_total': net, 'line_tax': amount_tax})
    return result


@transaction.atomic
def save_order(user, company_id, domain, payload, pk=None):
    company = access(user, company_id, domain, 'edit' if pk else 'create', True)
    model, line_model, kind = models_for(domain)
    serializer = OrderInput(data=payload); serializer.is_valid(raise_exception=True)
    data = dict(serializer.validated_data)
    if pk:
        obj = get_order(company_id, domain, pk)
        if 'version' not in data: raise ValidationError({'version': 'Version requise.'})
        check_version(obj, data['version'])
        if obj.status != 'draft': raise ValidationError('Seul un brouillon peut être modifié. Rouvrez le document avant confirmation.')
        if domain == 'sales' and obj.lead_id != data.get('lead_id'): raise ValidationError('Le prospect source d’un devis doit être conservé.')
    else:
        if 'request_key' not in data: raise ValidationError({'request_key': 'Clé de création requise.'})
        fingerprint = hashlib.sha256(json.dumps(data, sort_keys=True, cls=DjangoJSONEncoder).encode()).hexdigest()
        previous = model.objects.filter(company=company, request_key=data['request_key']).first()
        if previous:
            if previous.payload_hash != fingerprint: raise ValidationError('Clé de création déjà utilisée avec un contenu différent.')
            return previous, False
        obj = None
    partner, lead = checked_relations(user, company, domain, data)
    lines = prepare_lines(company, domain, data['lines'])
    totals = document_totals(lines, company.currency_code)
    fields = {name: data[name] for name in ['partner_id', 'warehouse_id', 'order_date', 'notes']}
    fields.update(totals)
    if domain == 'sales': fields['lead'] = lead
    if obj:
        from approvals.services import invalidate_requests
        invalidate_requests(obj, domain)
        before = {'version': obj.version, 'total_amount': obj.total_amount}
        obj.version += 1
        for name, value in fields.items(): setattr(obj, name, value)
        obj.save()
    else:
        before = None
        obj = model.objects.create(company=company, created_by=user, currency_code=company.currency_code, reference=next_reference(company, kind), request_key=data['request_key'], payload_hash=fingerprint, **fields)
    line_model.objects.bulk_create([line_model(company=company, order=obj, document_version=obj.version, **line) for line in lines])
    if lead and lead.partner_id is None:
        lead.partner = partner; lead.save(update_fields=['partner', 'updated_at'])
    if lead: audit(company, user, 'crm.lead_quoted', lead, after={'order_id': obj.pk, 'reference': obj.reference})
    audit(company, user, f'{domain}.order_updated' if pk else f'{domain}.order_created', obj, before, {'version': obj.version, 'total_amount': obj.total_amount, 'reference': obj.reference})
    return obj, True


def validate_confirmable(company, obj):
    if obj.partner.status != 'active' or not obj.warehouse.active: raise ValidationError('Client/fournisseur ou entrepôt archivé.')
    if not getattr(obj.partner, 'is_customer' if obj._meta.app_label == 'sales' else 'is_supplier'): raise ValidationError('Le partenaire ne remplit plus le rôle requis.')
    lines = current_lines(obj)
    if not lines: raise ValidationError('Au moins une ligne est requise.')
    for line in lines:
        if not line.product.active or line.product.type != line.product_type or line.product.unit_id != line.unit_id_snapshot:
            raise ValidationError('Un produit est archivé ou son unité/type a changé. Révisez le brouillon.')
    return lines


@transaction.atomic
def order_action(user, company_id, domain, pk, action, version, reason='', closure_version=None):
    permission = {'submit': 'submit', 'confirm': 'confirm', 'cancel': 'cancel', 'reopen': 'edit', 'reserve': 'reserve', 'complete': 'complete', 'resume': 'resume'}.get(action)
    if not permission or (action == 'reserve' and domain != 'sales'): raise NotFound()
    company = access(user, company_id, domain, permission, True)
    obj = get_order(company_id, domain, pk); check_version(obj, version)
    if action == 'resume' and not 8 <= len(reason.strip()) <= 1000: raise ValidationError({'reason': 'Motif requis de 8 à 1000 caractères.'})
    if action in ('complete', 'resume'):
        if closure_version is None: raise ValidationError({'closure_version': 'Version du cycle de clôture requise.'})
        expected_status = 'completed' if action == 'complete' else 'confirmed'
        if obj.closure_version == closure_version + 1 and obj.status == expected_status: return obj
        if obj.closure_version != closure_version: raise Conflict('Le cycle de clôture a changé. Rechargez la commande.')
    from approvals.services import approval_state, submit_request, invalidate_requests
    if action == 'complete':
        if obj.status != 'confirmed': raise ValidationError('Seule une commande confirmée peut être clôturée.')
        from .completion import completion_state
        state = completion_state(user, obj, domain)
        if state is None: raise PermissionDenied('Les droits de consultation des exécutions et des documents financiers sont requis pour clôturer.')
        if not state['eligible']: raise ValidationError(state['reasons'])
        obj.status = 'completed'; obj.completed_at = timezone.now(); obj.completed_by = user
        obj.closure_version += 1
        obj.save(update_fields=['status', 'completed_at', 'completed_by', 'closure_version', 'updated_at'])
    elif action == 'resume':
        reason = reason.strip()
        if not 8 <= len(reason) <= 1000: raise ValidationError({'reason': 'Motif requis de 8 à 1000 caractères.'})
        if obj.status != 'completed': raise ValidationError('Seule une commande clôturée peut être reprise.')
        before = {'status': obj.status, 'completed_at': obj.completed_at, 'completed_by': obj.completed_by_id}
        obj.status = 'confirmed'; obj.completed_at = None; obj.completed_by = None
        obj.closure_version += 1
        obj.save(update_fields=['status', 'completed_at', 'completed_by', 'closure_version', 'updated_at'])
        audit(company, user, f'{domain}.order_resume', obj, before, {'status': obj.status, 'version': obj.version, 'closure_version': obj.closure_version, 'reason': reason})
        return obj
    elif action in ('submit', 'confirm'):
        if obj.status in ('confirmed', 'completed'): return obj
        if obj.status not in ('draft', 'pending_approval'): raise ValidationError('Ce document ne peut pas être confirmé ou soumis.')
        validate_confirmable(company, obj)
        rule, approved = approval_state(obj, domain)
        if action == 'submit':
            if rule and not approved: submit_request(user, obj, domain, rule)
            return obj
        if rule and not approved: raise ValidationError('L’approbation de la version courante est requise avant confirmation.')
        invalidate_requests(obj, domain, pending_only=True)
        obj.status = 'confirmed'; obj.confirmed_at = timezone.now(); obj.save(update_fields=['status', 'confirmed_at', 'updated_at'])
        if domain == 'sales':
            from sales.reservations import reserve_order
            reserve_order(company, user, obj)
    elif action == 'reopen':
        if obj.status == 'draft': return obj
        if obj.status != 'pending_approval': raise ValidationError('Un document confirmé ou annulé ne peut pas être rouvert.')
        invalidate_requests(obj, domain); obj.status = 'draft'; obj.save(update_fields=['status', 'updated_at'])
    elif action == 'cancel':
        if obj.status == 'cancelled': return obj
        if obj.status == 'completed': raise ValidationError('Une commande terminée nécessite une correction traçable.')
        if domain == 'sales' and obj.invoices.filter(status='validated').exists(): raise ValidationError('Une facture validée interdit l’annulation de cette commande.')
        from inventory.fulfillment import has_validated_effects
        if has_validated_effects(obj, domain): raise ValidationError('Une réception ou livraison validée interdit l’annulation de cette commande.')
        if domain == 'sales':
            from sales.reservations import release_order
            release_order(company, user, obj)
        invalidate_requests(obj, domain); obj.status = 'cancelled'; obj.save(update_fields=['status', 'updated_at'])
    else:
        if obj.status != 'confirmed': raise ValidationError('Seule une commande confirmée peut réserver le stock manquant.')
        validate_confirmable(company, obj)
        from sales.reservations import reserve_order
        reserve_order(company, user, obj)
    facts = {'version': obj.version, 'status': obj.status, 'reference': obj.reference}
    if action == 'complete': facts.update({'closure_version': obj.closure_version, 'completed_at': obj.completed_at, 'completed_by': obj.completed_by_id})
    audit(company, user, f'{domain}.order_{action}', obj, after=facts)
    return obj
