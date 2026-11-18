from decimal import Decimal
from django.db.models import DecimalField, OuterRef, Subquery, Sum, Value, F, ExpressionWrapper
from django.db.models.functions import Coalesce, Greatest
from .models import CreditNote, PaymentAllocation

MONEY = DecimalField(max_digits=44, decimal_places=6)


def invoice_balances(query):
    credits = CreditNote.objects.filter(company_id=OuterRef('company_id'), invoice_id=OuterRef('pk'), status='validated').order_by().values('invoice_id').annotate(total=Sum('total_amount')).values('total')
    allocations = PaymentAllocation.objects.filter(company_id=OuterRef('company_id'), invoice_id=OuterRef('pk'), status='active', payment__status='validated').order_by().values('invoice_id').annotate(total=Sum('amount')).values('total')
    zero = Value(Decimal(0), output_field=MONEY)
    return query.annotate(credited_total=Coalesce(Subquery(credits, output_field=MONEY), zero), allocated_total=Coalesce(Subquery(allocations, output_field=MONEY), zero)).annotate(net_total=ExpressionWrapper(F('total_amount') - F('credited_total'), output_field=MONEY)).annotate(outstanding=Greatest(F('net_total') - F('allocated_total'), zero, output_field=MONEY), customer_credit=Greatest(F('allocated_total') - F('net_total'), zero, output_field=MONEY))
