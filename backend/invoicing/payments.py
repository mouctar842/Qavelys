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
from core.money import rounded
from core.order_serializers import ExactDecimalField
from core.services import require_membership
from reference.models import Partner
from .models import Invoice, Payment, PaymentAllocation


def access(user, company_id, action='view', lock=False):
    code = f'invoicing.payment.{action}'
    company = locked_company(user, company_id, code) if lock else require_membership(user, company_id, code).company
    require_membership(user, company_id, 'invoicing.payment.view')
    if action in ('allocate', 'reverse_allocation'): require_membership(user, company_id, 'invoicing.invoice.view')
    require_module(company_id, 'invoicing')
    return company


def invoice_balance(invoice):
    with localcontext() as ctx:
        ctx.prec = 60
        credited = invoice.credit_notes.filter(status='validated').aggregate(total=Sum('total_amount'))['total'] or Decimal(0)
        paid = invoice.payment_allocations.filter(status='active', payment__status='validated').aggregate(total=Sum('amount'))['total'] or Decimal(0)
        net = invoice.total_amount - credited
        due, credit = max(net - paid, Decimal(0)), max(paid - net, Decimal(0))
        state = 'not_applicable' if invoice.status != 'validated' else 'paid' if due == 0 else 'overdue' if invoice.due_date < timezone.localdate() else 'partial' if paid > 0 else 'unpaid'
        return {'credited_amount': credited, 'net_amount': net, 'paid_amount': paid, 'amount_due': due if invoice.status == 'validated' else Decimal(0), 'credit_balance': credit, 'payment_status': state}


def allocated_amount(payment):
    return payment.allocations.filter(status='active').aggregate(total=Sum('amount'))['total'] or Decimal(0)


def available_amount(payment):
    with localcontext() as ctx:
        ctx.prec = 60
        return payment.amount - allocated_amount(payment) if payment.status == 'validated' else Decimal(0)


def exact_amount(value, currency):
    if value <= 0 or rounded(value, currency) != value: raise ValidationError('Montant positif requis à la précision de la devise, sans arrondi implicite.')
    return value


class PaymentInput(serializers.Serializer):
    request_key = serializers.UUIDField()
    partner_id = serializers.UUIDField()
    amount = ExactDecimalField(max_digits=44, decimal_places=6, min_value=Decimal('0.000001'))
    method = serializers.ChoiceField(choices=['bank_transfer', 'cash', 'card', 'mobile_money', 'other'])
    payment_date = serializers.DateField()
    external_reference = serializers.CharField(allow_blank=True, default='', max_length=200)
    notes = serializers.CharField(allow_blank=True, default='', max_length=4000)


class AllocationInput(serializers.Serializer):
    invoice_id = serializers.UUIDField()
    amount = ExactDecimalField(max_digits=44, decimal_places=6, min_value=Decimal('0.000001'))


class BatchInput(serializers.Serializer):
    request_key = serializers.UUIDField()
    allocations = AllocationInput(many=True, allow_empty=False, max_length=100)


class ReasonInput(serializers.Serializer):
    reason = serializers.CharField(max_length=4000)


def fingerprint(data): return hashlib.sha256(json.dumps(data, sort_keys=True, cls=DjangoJSONEncoder).encode()).hexdigest()


def get_payment(company_id, pk, lock=False):
    query = Payment.objects.select_related('partner').filter(company_id=company_id, pk=pk)
    if lock: query = query.select_for_update(of=('self',))
    obj = query.first()
    if obj is None: raise NotFound()
    return obj


@transaction.atomic
def create_payment(user, company_id, payload):
    company = access(user, company_id, 'create', True)
    serializer = PaymentInput(data=payload); serializer.is_valid(raise_exception=True)
    data = dict(serializer.validated_data); digest = fingerprint(data)
    previous = Payment.objects.filter(company=company, request_key=data['request_key']).first()
    if previous:
        if previous.payload_hash != digest: raise ValidationError('Clé de création déjà utilisée avec un contenu différent.')
        return previous, False
    if not Partner.objects.filter(company=company, pk=data['partner_id'], is_customer=True, status='active').exists(): raise ValidationError('Client actif introuvable dans cette entreprise.')
    exact_amount(data['amount'], company.currency_code)
    obj = Payment.objects.create(company=company, created_by=user, currency_code=company.currency_code, reference=next_reference(company, 'payment'), payload_hash=digest, **data)
    audit(company, user, 'invoicing.payment_created', obj, after={'reference': obj.reference, 'amount': obj.amount})
    return obj, True


@transaction.atomic
def payment_action(user, company_id, pk, action, payload):
    if action not in ('validate', 'cancel'): raise NotFound()
    company = access(user, company_id, action, True)
    obj = get_payment(company_id, pk, True)
    if action == 'validate':
        if obj.status == 'validated': return obj
        if obj.status != 'draft': raise ValidationError('Seul un brouillon peut être validé.')
        if obj.partner.status != 'active' or not obj.partner.is_customer: raise ValidationError('Le client doit être actif.')
        exact_amount(obj.amount, obj.currency_code)
        obj.partner_snapshot = {name: getattr(obj.partner, name) for name in ['name', 'email', 'phone', 'address']}
        obj.status = 'validated'; obj.validated_at = timezone.now()
    else:
        if obj.status == 'cancelled': return obj
        if allocated_amount(obj) > 0: raise ValidationError('Extournez les allocations actives avant d’annuler cet enregistrement.')
        if obj.status == 'validated':
            reason = ReasonInput(data=payload); reason.is_valid(raise_exception=True)
            obj.cancellation_reason = reason.validated_data['reason']
        obj.status = 'cancelled'
    obj.save()
    audit(company, user, f'invoicing.payment_{action}', obj, after={'reference': obj.reference, 'amount': obj.amount, 'reason': obj.cancellation_reason})
    return obj


@transaction.atomic
def allocate(user, company_id, pk, payload):
    company = access(user, company_id, 'allocate', True)
    payment = get_payment(company_id, pk, True)
    serializer = BatchInput(data=payload); serializer.is_valid(raise_exception=True)
    data = dict(serializer.validated_data); digest = fingerprint(data)
    previous = list(payment.allocations.filter(request_key=data['request_key']).order_by('invoice_id'))
    if previous:
        if any(row.payload_hash != digest for row in previous): raise ValidationError('Cette clé d’allocation possède déjà un autre contenu.')
        return payment, previous, False
    if payment.status != 'validated': raise ValidationError('Un paiement validé est requis.')
    ids = [row['invoice_id'] for row in data['allocations']]
    if len(ids) != len(set(ids)): raise ValidationError('Une seule occurrence par facture dans un lot.')
    invoices = {obj.pk: obj for obj in Invoice.objects.select_for_update().filter(company=company, pk__in=ids).order_by('id')}
    with localcontext() as ctx:
        ctx.prec = 60
        total = sum((exact_amount(row['amount'], payment.currency_code) for row in data['allocations']), Decimal(0))
        if total > available_amount(payment): raise ValidationError('Montant supérieur au disponible du paiement.')
        for row in data['allocations']:
            invoice = invoices.get(row['invoice_id'])
            if invoice is None or invoice.status != 'validated' or invoice.partner_id != payment.partner_id or invoice.currency_code != payment.currency_code: raise ValidationError('Facture validée du même client, de la même devise et de cette entreprise requise.')
            if row['amount'] > invoice_balance(invoice)['amount_due']: raise ValidationError(f'Montant supérieur au dû de {invoice.reference}.')
        result = []
        for row in data['allocations']:
            obj = PaymentAllocation.objects.create(company=company, payment=payment, created_by=user, request_key=data['request_key'], payload_hash=digest, **row)
            audit(company, user, 'invoicing.payment_allocated', obj, after={'payment_id': payment.pk, 'invoice_id': obj.invoice_id, 'amount': obj.amount})
            result.append(obj)
    return payment, result, True


@transaction.atomic
def reverse_allocation(user, company_id, pk, payload):
    company = access(user, company_id, 'reverse_allocation', True)
    obj = PaymentAllocation.objects.select_for_update().filter(company=company, pk=pk).first()
    if obj is None: raise NotFound()
    if obj.status == 'reversed': return obj
    serializer = ReasonInput(data=payload); serializer.is_valid(raise_exception=True)
    obj.status = 'reversed'; obj.reversed_by = user; obj.reversed_at = timezone.now(); obj.reversal_reason = serializer.validated_data['reason']; obj.save()
    audit(company, user, 'invoicing.allocation_reversed', obj, after={'payment_id': obj.payment_id, 'invoice_id': obj.invoice_id, 'amount': obj.amount, 'reason': obj.reversal_reason})
    return obj
