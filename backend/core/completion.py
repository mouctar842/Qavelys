from decimal import Decimal
from core.administration import require_module
from core.services import permissions_for, require_membership


def can_inspect(user, company_id, domain):
    member = require_membership(user, company_id, f'{domain}.order.view')
    permissions = set(permissions_for(member))
    required = {f'{domain}.order.complete', f'inventory.{"delivery" if domain == "sales" else "receipt"}.view'}
    if domain == 'sales': required.update({'invoicing.invoice.view', 'invoicing.payment.view', 'invoicing.credit_note.view'})
    return required <= permissions


def completion_state(user, order, domain):
    # Ne pas exposer un solde financier à un lecteur commercial sans ces droits.
    if not can_inspect(user, order.company_id, domain):
        return None
    from core.orders import current_lines
    from inventory.fulfillment import executed_quantities
    require_module(order.company_id, 'inventory')
    if domain == 'sales': require_module(order.company_id, 'invoicing')
    lines = current_lines(order)
    executed = executed_quantities(order, domain)
    reasons = []
    if not lines or any(executed.get(line.pk, Decimal(0)) != line.quantity for line in lines):
        reasons.append('Toutes les quantités doivent être livrées.' if domain == 'sales' else 'Toutes les quantités doivent être reçues.')
    documents = order.deliveries if domain == 'sales' else order.receipts
    if documents.filter(status='draft').exists(): reasons.append('Des documents d’exécution sont encore en brouillon.')
    if domain == 'sales':
        from invoicing.services import billed_quantities
        from invoicing.payments import invoice_balance
        from invoicing.models import CreditNote
        from inventory.models import StockReservation
        billed = billed_quantities(order)
        if not lines or any(billed.get(line.pk, Decimal(0)) != line.quantity for line in lines): reasons.append('Toutes les quantités doivent être facturées nettes des avoirs.')
        if order.invoices.filter(status='draft').exists() or CreditNote.objects.filter(company_id=order.company_id, invoice__sales_order=order, status='draft').exists(): reasons.append('Des factures ou avoirs liés sont encore en brouillon.')
        if StockReservation.objects.filter(company_id=order.company_id, sales_order_line__order=order, status='active', quantity__gt=0).exists(): reasons.append('Une réservation de stock reste active.')
        balances = [invoice_balance(invoice) for invoice in order.invoices.filter(status='validated')]
        if any(row['amount_due'] != 0 for row in balances): reasons.append('Toutes les factures liées doivent être intégralement réglées.')
        if any(row['credit_balance'] != 0 for row in balances): reasons.append('Un crédit client lié doit encore être régularisé.')
    return {'eligible': order.status == 'confirmed' and not reasons, 'reasons': reasons}
