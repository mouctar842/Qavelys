from django.db import transaction
from django.db.models import Sum
from rest_framework import serializers
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView
from core.administration import audit, locked_company, require_module
from core.models import CompanyModule
from core.services import permissions_for, require_membership
from .models import Partner
from .serializers import PartnerSerializer


class PrivateView(APIView):
    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response['Cache-Control'] = 'private, no-store'
        return response


class AddProfile(PrivateView):
    @transaction.atomic
    def post(self, request, company_id, pk):
        company = locked_company(request.user, company_id, 'contacts.manage')
        require_membership(request.user, company_id, 'contacts.view')
        require_module(company_id, 'contacts')
        class Input(serializers.Serializer):
            profile = serializers.ChoiceField(choices=['customer', 'supplier'])
        data = Input(data=request.data); data.is_valid(raise_exception=True)
        if set(request.data) != {'profile'}: raise ValidationError('Seul le profil est attendu.')
        obj = Partner.objects.filter(company=company, pk=pk).first()
        if obj is None: raise NotFound()
        if obj.status != 'active': raise ValidationError('Réactivez ce tiers avant de lui ajouter un profil.')
        field = 'is_' + data.validated_data['profile']
        if not getattr(obj, field):
            before = PartnerSerializer(obj).data
            setattr(obj, field, True); obj.save(update_fields=[field, 'updated_at'])
            audit(company, request.user, 'partners.updated', obj, before, PartnerSerializer(obj).data)
        return Response(PartnerSerializer(obj).data)


def sections():
    from crm.models import Lead
    from sales.models import SalesOrder
    from purchases.models import PurchaseOrder
    from inventory.models import Delivery, GoodsReceipt
    from invoicing.models import Invoice, Payment
    return {
        'opportunities': ('customer', 'crm', 'crm.view', 'Opportunités', Lead, 'partner_id', 'created_at', 'title', 'stage'),
        'sales': ('customer', 'sales', 'sales.order.view', 'Devis et commandes', SalesOrder, 'partner_id', 'order_date', 'reference', 'status'),
        'deliveries': ('customer', 'inventory', 'inventory.delivery.view', 'Livraisons', Delivery, 'sales_order__partner_id', 'created_at', 'reference', 'status'),
        'invoices': ('customer', 'invoicing', 'invoicing.invoice.view', 'Factures', Invoice, 'partner_id', 'issue_date', 'reference', 'status'),
        'payments': ('customer', 'invoicing', 'invoicing.payment.view', 'Paiements', Payment, 'partner_id', 'payment_date', 'reference', 'status'),
        'purchases': ('supplier', 'purchases', 'purchases.order.view', 'Commandes fournisseurs', PurchaseOrder, 'partner_id', 'order_date', 'reference', 'status'),
        'receipts': ('supplier', 'inventory', 'inventory.receipt.view', 'Réceptions', GoodsReceipt, 'purchase_order__partner_id', 'created_at', 'reference', 'status'),
    }


class Activity(PrivateView):
    def get(self, request, company_id, pk):
        member = require_membership(request.user, company_id, 'contacts.view')
        require_module(company_id, 'contacts')
        profile = request.query_params.get('profile', '')
        if profile not in ('customer', 'supplier'): raise ValidationError('Profil client ou fournisseur requis.')
        obj = Partner.objects.filter(company_id=company_id, pk=pk, **{'is_' + profile: True}).first()
        if obj is None: raise NotFound()
        rights = set(permissions_for(member))
        modules = set(CompanyModule.objects.filter(company_id=company_id, enabled=True, module__status='available').values_list('module__code', flat=True))
        allowed = {code: config for code, config in sections().items() if config[0] == profile and config[1] in modules and config[2] in rights}
        for code, domain in [('deliveries', 'sales'), ('receipts', 'purchases')]:
            if domain not in modules or f'{domain}.order.view' not in rights:
                allowed.pop(code, None)
        section = request.query_params.get('section') or next(iter(allowed), None)
        if section and section not in allowed: raise PermissionDenied('Cette activité nécessite le module et la permission correspondants.')
        try:
            page = int(request.query_params.get('page', 1))
            if not 1 <= page <= 1000000: raise ValueError()
        except ValueError: raise ValidationError('Page invalide.')
        result = {'available_sections': [{'code': code, 'label': config[3]} for code, config in allowed.items()], 'section': section, 'count': 0, 'page': page, 'results': []}
        if section:
            _, _, _, _, model, field, date_field, title_field, status_field = allowed[section]
            query = model.objects.filter(company_id=company_id, **{field: obj.pk}).order_by('-' + date_field, '-id')
            result['count'] = query.count()
            rows = []
            for item in query[(page - 1) * 25:page * 25]:
                row = {'id': item.pk, 'label': getattr(item, title_field), 'date': getattr(item, date_field), 'status': getattr(item, status_field)}
                if section in ('deliveries', 'receipts'):
                    row['source_order_id'] = item.sales_order_id if section == 'deliveries' else item.purchase_order_id
                if hasattr(item, 'currency_code'):
                    row.update(currency_code=item.currency_code, amount=str(item.amount if section == 'payments' else item.total_amount))
                rows.append(row)
            result['results'] = rows
        if profile == 'customer' and 'invoicing' in modules and {'invoicing.invoice.view', 'invoicing.payment.view', 'invoicing.credit_note.view'} <= rights:
            from invoicing.models import Invoice
            from invoicing.queries import invoice_balances
            query = invoice_balances(Invoice.objects.filter(company_id=company_id, partner=obj, status='validated'))
            result['balances'] = [{'currency_code': row['currency_code'], 'amount_due': str(row['amount_due']), 'credit_balance': str(row['credit_balance'])} for row in query.values('currency_code').annotate(amount_due=Sum('outstanding'), credit_balance=Sum('customer_credit')).order_by('currency_code')]
        return Response(result)
