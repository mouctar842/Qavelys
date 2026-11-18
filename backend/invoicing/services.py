import hashlib
import json
from decimal import Decimal, localcontext
from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import NotFound, ValidationError
from core.administration import audit, locked_company, next_reference, require_module
from core.money import document_totals, exact_line
from core.order_serializers import ExactDecimalField
from core.orders import get_order, current_lines, check_version, prepare_lines, Conflict
from core.services import require_membership
from reference.models import Partner
from .models import Invoice, InvoiceLine, CreditNote, CreditNoteLine


def config(kind):
    if kind == 'invoices': return Invoice, 'invoice'
    if kind == 'credit-notes': return CreditNote, 'credit_note'
    raise NotFound()


def access(user, company_id, kind, action='view', lock=False):
    _, code = config(kind)
    permission = f'invoicing.{code}.{action}'
    company = locked_company(user, company_id, permission) if lock else require_membership(user, company_id, permission).company
    require_membership(user, company_id, f'invoicing.{code}.view')
    if kind == 'credit-notes': require_membership(user, company_id, 'invoicing.invoice.view')
    require_module(company_id, 'invoicing')
    return company


def invoice_get(company_id, pk):
    obj = Invoice.objects.select_related('partner', 'sales_order', 'company__companysettings').filter(company_id=company_id, pk=pk).first()
    if obj is None: raise NotFound()
    return obj


def billed_quantities(order):
    billed = {row['sales_order_line_id']: row['total'] for row in InvoiceLine.objects.filter(company_id=order.company_id, invoice__sales_order=order, invoice__status='validated').values('sales_order_line_id').annotate(total=Sum('quantity'))}
    for row in CreditNoteLine.objects.filter(company_id=order.company_id, credit_note__status='validated', invoice_line__invoice__sales_order=order).values('invoice_line__sales_order_line_id').annotate(total=Sum('quantity')):
        pk = row['invoice_line__sales_order_line_id']; billed[pk] = billed.get(pk, Decimal(0)) - row['total']
    return billed


def check_order_quota(order, lines):
    sources = {line.pk: line for line in current_lines(order)}
    billed = billed_quantities(order)
    ids = [line.get('sales_order_line_id') for line in lines]
    if len(ids) != len(set(ids)): raise ValidationError('Une seule occurrence par ligne de commande.')
    for line in lines:
        source = sources.get(line.get('sales_order_line_id'))
        if source is None: raise ValidationError('Ligne absente de la version confirmée de cette commande.')
        if line['quantity'] > source.quantity - billed.get(source.pk, Decimal(0)): raise ValidationError(f'Quantité facturable dépassée pour {source.product_name}.')
    return sources


class LineInput(serializers.Serializer):
    sales_order_line_id = serializers.UUIDField(required=False)
    product_id = serializers.UUIDField(required=False, allow_null=True)
    description = serializers.CharField(required=False, allow_blank=True, max_length=4000)
    quantity = ExactDecimalField(max_digits=20, decimal_places=6, min_value=Decimal('0.000001'))
    unit_price = ExactDecimalField(max_digits=20, decimal_places=6, min_value=Decimal(0), required=False)
    discount_rate = ExactDecimalField(max_digits=9, decimal_places=4, min_value=Decimal(0), max_value=Decimal(100), default=Decimal(0))
    tax_rate = ExactDecimalField(max_digits=9, decimal_places=4, min_value=Decimal(0), max_value=Decimal(100), required=False)


class InvoiceInput(serializers.Serializer):
    request_key = serializers.UUIDField()
    partner_id = serializers.UUIDField()
    sales_order_id = serializers.UUIDField(allow_null=True, default=None)
    order_version = serializers.IntegerField(min_value=1, required=False)
    issue_date = serializers.DateField()
    due_date = serializers.DateField()
    notes = serializers.CharField(allow_blank=True, default='', max_length=10000)
    lines = LineInput(many=True, allow_empty=False, max_length=200)


class CreditLineInput(serializers.Serializer):
    invoice_line_id = serializers.UUIDField()
    quantity = ExactDecimalField(max_digits=20, decimal_places=6, min_value=Decimal('0.000001'))


class CreditInput(serializers.Serializer):
    request_key = serializers.UUIDField()
    invoice_id = serializers.UUIDField()
    issue_date = serializers.DateField()
    reason = serializers.CharField(max_length=4000)
    notes = serializers.CharField(allow_blank=True, default='', max_length=10000)
    lines = CreditLineInput(many=True, allow_empty=False, max_length=200)


def credit_quantities(invoice):
    return {row['invoice_line_id']: row['total'] for row in CreditNoteLine.objects.filter(company_id=invoice.company_id, credit_note__invoice=invoice, credit_note__status='validated').values('invoice_line_id').annotate(total=Sum('quantity'))}


def credit_totals(invoice, inputs):
    if invoice.status != 'validated': raise ValidationError('Une facture validée est requise.')
    sources = {line.pk: line for line in invoice.lines.all()}
    quantities = credit_quantities(invoice)
    ids = [line['invoice_line_id'] for line in inputs]
    if len(ids) != len(set(ids)): raise ValidationError('Une seule occurrence par ligne de facture.')
    for line in inputs:
        source = sources.get(line['invoice_line_id'])
        if source is None: raise ValidationError('Ligne extérieure à cette facture.')
        current = quantities.get(source.pk, Decimal(0))
        if current + line['quantity'] > source.quantity: raise ValidationError('Quantité créditée supérieure à la quantité facturée.')
        quantities[source.pk] = current + line['quantity']
    totals = document_totals([{'quantity': quantity, 'unit_price': sources[pk].unit_price, 'discount_rate': sources[pk].discount_rate, 'tax_rate': sources[pk].tax_rate} for pk, quantity in quantities.items() if quantity > 0], invoice.currency_code)
    previous = invoice.credit_notes.filter(status='validated').aggregate(untaxed_amount=Sum('untaxed_amount'), tax_amount=Sum('tax_amount'), total_amount=Sum('total_amount'))
    with localcontext() as ctx:
        ctx.prec = 60
        return {key: value - (previous[key] or Decimal(0)) for key, value in totals.items()}


def linked_order(user, company, pk, version):
    require_membership(user, company.pk, 'sales.order.view'); require_module(company.pk, 'sales')
    order = get_order(company.pk, 'sales', pk)
    if version is None: raise ValidationError('Version de commande requise.')
    check_version(order, version)
    if order.status not in ('confirmed', 'completed'): raise ValidationError('Une commande confirmée est requise.')
    return order


@transaction.atomic
def create_document(user, company_id, kind, payload):
    company = access(user, company_id, kind, 'create', True)
    model, code = config(kind)
    serializer = (InvoiceInput if kind == 'invoices' else CreditInput)(data=payload); serializer.is_valid(raise_exception=True)
    data = dict(serializer.validated_data)
    fingerprint = hashlib.sha256(json.dumps(data, sort_keys=True, cls=DjangoJSONEncoder).encode()).hexdigest()
    previous = model.objects.filter(company=company, request_key=data['request_key']).first()
    if previous:
        if previous.payload_hash != fingerprint: raise ValidationError('Clé de création déjà utilisée avec un contenu différent.')
        return previous, False
    if kind == 'invoices':
        if data['due_date'] < data['issue_date']: raise ValidationError('Échéance antérieure à l’émission.')
        partner = Partner.objects.filter(company=company, pk=data['partner_id'], status='active', is_customer=True).first()
        if partner is None: raise ValidationError('Client actif introuvable dans cette entreprise.')
        order = linked_order(user, company, data['sales_order_id'], data.get('order_version')) if data['sales_order_id'] else None
        if order and (order.partner_id != partner.pk or order.currency_code != company.currency_code): raise ValidationError('Client ou devise différents de la commande.')
        lines = []
        sources = check_order_quota(order, data['lines']) if order else {}
        for position, item in enumerate(data['lines'], 1):
            if order:
                source = sources[item['sales_order_line_id']]
                line = {name: getattr(source, name) for name in ['product_id', 'product_name', 'unit_name', 'description', 'unit_price', 'discount_rate', 'tax_rate']}
                line['sales_order_line_id'] = source.pk
            elif item.get('sales_order_line_id'): raise ValidationError('Une ligne de commande exige une commande source.')
            elif item.get('product_id'):
                require_module(company.pk, 'catalog')
                prepared = prepare_lines(company, 'sales', [item])[0]
                line = {name: prepared[name] for name in ['product', 'product_name', 'unit_name', 'description', 'unit_price', 'discount_rate', 'tax_rate']}
            else:
                if not item.get('description') or 'unit_price' not in item: raise ValidationError('Description et prix requis pour une ligne libre.')
                line = {'description': item['description'], 'unit_price': item['unit_price'], 'discount_rate': item['discount_rate'], 'tax_rate': item.get('tax_rate', Decimal(0))}
            line.update(position=position, quantity=item['quantity'])
            line['line_total'], line['line_tax'] = exact_line(item['quantity'], line['unit_price'], line['discount_rate'], line['tax_rate'])
            lines.append(line)
        totals = document_totals(lines, company.currency_code)
        obj = Invoice.objects.create(company=company, partner=partner, sales_order=order, order_version=order.version if order else None, due_date=data['due_date'], currency_code=company.currency_code, reference=next_reference(company, code), request_key=data['request_key'], payload_hash=fingerprint, issue_date=data['issue_date'], notes=data['notes'], created_by=user, **totals)
        InvoiceLine.objects.bulk_create([InvoiceLine(company=company, invoice=obj, **line) for line in lines])
    else:
        invoice = invoice_get(company.pk, data['invoice_id'])
        if data['issue_date'] < invoice.issue_date: raise ValidationError('L’avoir ne peut pas précéder sa facture.')
        totals = credit_totals(invoice, data['lines'])
        obj = CreditNote.objects.create(company=company, invoice=invoice, reason=data['reason'], currency_code=invoice.currency_code, reference=next_reference(company, code), request_key=data['request_key'], payload_hash=fingerprint, issue_date=data['issue_date'], notes=data['notes'], created_by=user, **totals)
        sources = {line.pk: line for line in invoice.lines.all()}
        CreditNoteLine.objects.bulk_create([CreditNoteLine(company=company, credit_note=obj, amount=exact_line(line['quantity'], sources[line['invoice_line_id']].unit_price, sources[line['invoice_line_id']].discount_rate, sources[line['invoice_line_id']].tax_rate)[0], **line) for line in data['lines']])
    audit(company, user, f'invoicing.{code}_created', obj, after={'reference': obj.reference, 'total_amount': obj.total_amount})
    return obj, True


@transaction.atomic
def document_action(user, company_id, kind, pk, action):
    if action not in ('validate', 'cancel'): raise NotFound()
    company = access(user, company_id, kind, action, True)
    model, code = config(kind)
    obj = model.objects.filter(company=company, pk=pk).first()
    if obj is None: raise NotFound()
    if action == 'cancel':
        if obj.status == 'validated': raise ValidationError('Un document validé est immuable ; créez un avoir pour corriger une facture.')
        if obj.status == 'cancelled': return obj
        obj.status = 'cancelled'; obj.save(update_fields=['status', 'updated_at'])
    else:
        if obj.status == 'validated': return obj
        if obj.status != 'draft': raise ValidationError('Seul un brouillon peut être validé.')
        if kind == 'invoices':
            if obj.partner.status != 'active' or not obj.partner.is_customer: raise ValidationError('Le client doit être actif.')
            if obj.sales_order_id:
                order = linked_order(user, company, obj.sales_order_id, obj.order_version)
                if order.partner_id != obj.partner_id or order.currency_code != obj.currency_code: raise ValidationError('Relation commande incohérente.')
                check_order_quota(order, list(obj.lines.values('sales_order_line_id', 'quantity')))
            settings = company.companysettings
            obj.issuer_snapshot = {'name': company.name, 'country_code': company.country_code, 'address': settings.address, 'phone': settings.phone}
            obj.partner_snapshot = {name: getattr(obj.partner, name) for name in ['name', 'email', 'phone', 'address']}
        else:
            totals = credit_totals(obj.invoice, list(obj.lines.values('invoice_line_id', 'quantity')))
            if any(getattr(obj, name) != amount for name, amount in totals.items()): raise Conflict('Les avoirs précédents ont changé les arrondis. Annulez puis recréez ce brouillon pour revoir les totaux.')
        obj.status = 'validated'; obj.validated_at = timezone.now(); obj.save()
    audit(company, user, f'invoicing.{code}_{action}', obj, after={'reference': obj.reference, 'total_amount': obj.total_amount})
    return obj
