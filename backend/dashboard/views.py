from datetime import datetime, time, timedelta, timezone as utc_timezone
from decimal import Decimal, localcontext
from django.db.models import Q, F, Sum, Count, Subquery, OuterRef, Value, DecimalField
from django.db.models.functions import Coalesce, Greatest, TruncMonth
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView
from core.administration import require_module
from core.services import require_membership, permissions_for
from core.models import CompanyModule, AuditLog
from reference.models import Partner, Product
from sales.models import SalesOrder, SalesOrderLine
from inventory.models import StockBalance, StockReservation, DeliveryLine
from invoicing.models import Invoice, CreditNote, Payment
from invoicing.queries import invoice_balances
from approvals.models import ApprovalRequest
from crm.models import CRMActivity

QUANTITY = DecimalField(max_digits=44, decimal_places=6)


def period(params):
    today = timezone.localdate()
    start = serializers.DateField().run_validation(params.get('start', today.replace(day=1).isoformat()))
    end = serializers.DateField().run_validation(params.get('end', today.isoformat()))
    if end < start or (end - start).days >= 366: raise ValidationError('Période ordonnée de 366 jours maximum requise.')
    try: after = end + timedelta(days=1)
    except OverflowError: raise ValidationError('Date de fin hors limites.')
    return start, end, datetime.combine(start, time.min, tzinfo=utc_timezone.utc), datetime.combine(after, time.min, tzinfo=utc_timezone.utc)


def sums(query, field):
    return [{'currency_code': row['currency_code'], 'amount': str(row['amount'] or Decimal(0))} for row in query.order_by().values('currency_code').annotate(amount=Sum(field)).order_by('currency_code')]


def revenue(invoices, credits, start, end):
    currencies = set(invoices.values_list('currency_code', flat=True)) | set(credits.values_list('currency_code', flat=True))
    totals, months = {}, {}
    for name, query in [('billed', invoices), ('credited', credits)]:
        for row in query.order_by().values('currency_code').annotate(total=Sum('total_amount')):
            totals.setdefault(row['currency_code'], {'billed': Decimal(0), 'credited': Decimal(0)})[name] = row['total']
        for row in query.order_by().annotate(month=TruncMonth('issue_date')).values('currency_code', 'month').annotate(total=Sum('total_amount')):
            key = (row['currency_code'], row['month'].strftime('%Y-%m'))
            months.setdefault(key, {'billed': Decimal(0), 'credited': Decimal(0)})[name] = row['total']
    result, series = [], []
    with localcontext() as ctx:
        ctx.prec = 60
        for code in sorted(currencies):
            amount = totals[code]
            result.append({'currency_code': code, 'billed': str(amount['billed']), 'credited': str(amount['credited']), 'net': str(amount['billed'] - amount['credited'])})
            month = start.replace(day=1)
            while True:
                values = months.get((code, month.strftime('%Y-%m')), {'billed': Decimal(0), 'credited': Decimal(0)})
                series.append({'currency_code': code, 'month': month.strftime('%Y-%m'), 'billed': str(values['billed']), 'credited': str(values['credited']), 'net': str(values['billed'] - values['credited'])})
                if month >= end.replace(day=1): break
                month = (month.replace(day=28) + timedelta(days=4)).replace(day=1)
    return result, series


def waiting_lines(company_id):
    delivered = DeliveryLine.objects.filter(company_id=company_id, order_line_id=OuterRef('pk'), document__status='validated').order_by().values('order_line_id').annotate(total=Sum('quantity')).values('total')
    reserved = StockReservation.objects.filter(company_id=company_id, sales_order_line_id=OuterRef('pk'), status='active').order_by().values('sales_order_line_id').annotate(total=Sum('quantity')).values('total')
    zero = Value(Decimal(0), output_field=QUANTITY)
    return SalesOrderLine.objects.filter(company_id=company_id, order__status='confirmed', document_version=F('order__version')).exclude(product_type='service').annotate(delivered=Coalesce(Subquery(delivered, output_field=QUANTITY), zero), reserved=Coalesce(Subquery(reserved, output_field=QUANTITY), zero)).annotate(waiting=Greatest(F('quantity') - F('delivered') - F('reserved'), zero, output_field=QUANTITY)).filter(waiting__gt=0)


class Overview(APIView):
    def get(self, request, company_id):
        member = require_membership(request.user, company_id, 'dashboard.view')
        require_module(company_id, 'dashboard')
        permissions = permissions_for(member)
        modules = set(CompanyModule.objects.filter(company_id=company_id, enabled=True).values_list('module__code', flat=True))
        allowed = lambda module, permission: module in modules and permission in permissions
        start, end, start_at, end_at = period(request.query_params)
        now = timezone.now(); today = timezone.localdate()
        sections = {}
        if allowed('contacts', 'contacts.view'):
            customers = Partner.objects.filter(company_id=company_id, is_customer=True, status='active')
            sections['contacts'] = {'active_customers': customers.count(), 'new_customers': customers.filter(created_at__gte=start_at, created_at__lt=end_at).count()}
        if allowed('sales', 'sales.order.view'):
            orders = SalesOrder.objects.filter(company_id=company_id, order_date__range=(start, end))
            confirmed = orders.filter(status__in=['confirmed', 'completed'])
            sections['sales'] = {'confirmed_count': confirmed.count(), 'draft_count': orders.filter(status__in=['draft', 'pending_approval']).count(), 'confirmed_totals': sums(confirmed, 'total_amount')}
        if allowed('invoicing', 'invoicing.invoice.view'):
            invoices = Invoice.objects.filter(company_id=company_id, status='validated')
            period_invoices = invoices.filter(issue_date__range=(start, end))
            credits = CreditNote.objects.filter(company_id=company_id, status='validated', issue_date__range=(start, end))
            totals, series = revenue(period_invoices, credits, start, end)
            unpaid = invoice_balances(invoices).filter(outstanding__gt=0)
            overdue = unpaid.filter(due_date__lt=today)
            sections['invoicing'] = {'invoice_count': period_invoices.count(), 'totals': totals, 'monthly': series, 'unpaid_count': unpaid.count(), 'amount_due': sums(unpaid, 'outstanding'), 'overdue_count': overdue.count(), 'overdue_amount': sums(overdue, 'outstanding'), 'overdue_invoices': [{'id': obj.pk, 'reference': obj.reference, 'partner_name': obj.partner_snapshot.get('name', obj.partner.name), 'due_date': obj.due_date, 'currency_code': obj.currency_code, 'amount_due': str(obj.outstanding)} for obj in overdue.select_related('partner').order_by('due_date', 'id')[:5]]}
        if allowed('invoicing', 'invoicing.payment.view'):
            payments = Payment.objects.filter(company_id=company_id, status='validated', payment_date__range=(start, end))
            sections['payments'] = {'count': payments.count(), 'totals': sums(payments, 'amount')}
        approval_types = []
        for domain, kind in [('sales', 'sales_order'), ('purchases', 'purchase_order')]:
            if allowed(domain, f'{domain}.order.view'): approval_types.append(kind)
        if 'approvals.requests.view' in permissions and approval_types:
            approvals = ApprovalRequest.objects.filter(company_id=company_id, status='pending', document_type__in=approval_types)
            sections['approvals'] = {'pending_count': approvals.count(), 'requests': [{'id': obj.pk, 'reference': obj.document_snapshot.get('reference', ''), 'document_version': obj.document_version, 'role_name': obj.rule_snapshot.get('role_name', '')} for obj in approvals.order_by('created_at', 'id')[:5]]}
        if allowed('inventory', 'inventory.view'):
            available = StockBalance.objects.filter(company_id=company_id, product_id=OuterRef('pk'), location__type='internal', location__active=True, location__warehouse__active=True).order_by().values('product_id').annotate(total=Sum(F('quantity') - F('reserved_quantity'), output_field=QUANTITY)).values('total')
            zero_stock = Product.objects.filter(company_id=company_id, active=True).exclude(type='service').annotate(available=Coalesce(Subquery(available, output_field=QUANTITY), Value(Decimal(0), output_field=QUANTITY))).filter(available__lte=0)
            inventory = {'unavailable_products': zero_stock.count(), 'products': list(zero_stock.order_by('name', 'id').values('id', 'name', 'sku')[:5])}
            if allowed('sales', 'sales.order.view'):
                waiting = waiting_lines(company_id)
                inventory.update(waiting_lines=waiting.count(), orders_waiting=[{'id': obj.order_id, 'reference': obj.order.reference, 'product_name': obj.product_name, 'waiting_quantity': str(obj.waiting), 'unit_name': obj.unit_name} for obj in waiting.select_related('order').order_by('order__order_date', 'position', 'id')[:5]])
            sections['inventory'] = inventory
        if allowed('crm', 'crm.view'):
            activities = CRMActivity.objects.filter(company_id=company_id, status='planned', due_at__lte=now)
            sections['crm'] = {'late_activities': activities.count(), 'activities': [{'id': obj.pk, 'lead_id': obj.lead_id, 'title': obj.lead.title, 'description': obj.description, 'due_at': obj.due_at} for obj in activities.select_related('lead').order_by('due_at', 'id')[:5]]}
        if 'audit.view' in permissions:
            sections['activity'] = [{'id': obj.pk, 'action': obj.action, 'actor': obj.actor.full_name, 'created_at': obj.created_at} for obj in AuditLog.objects.filter(company_id=company_id, created_at__gte=start_at, created_at__lt=end_at).select_related('actor').order_by('-created_at', '-id')[:8]]
        response = Response({'period': {'start': start, 'end': end, 'timezone': 'UTC'}, 'generated_at': now, 'sections': sections})
        response['Cache-Control'] = 'private, no-store'
        return response
