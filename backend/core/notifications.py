from django.db import transaction
from django.db.models import Q, F
from django.utils import timezone
from .models import Notification, CompanyModule
from .administration import locked_company, require_module
from .services import require_membership, permissions_for


def access(user, company_id, lock=False):
    if lock: locked_company(user, company_id, 'notifications.view')
    member = require_membership(user, company_id, 'notifications.view')
    require_module(company_id, 'core')
    return member


def sources(member):
    permissions = permissions_for(member)
    modules = set(CompanyModule.objects.filter(company_id=member.company_id, enabled=True).values_list('module__code', flat=True))
    domains = [domain for domain in ['sales', 'purchases'] if domain in modules and f'{domain}.order.view' in permissions]
    return permissions, modules, domains


def requests_for(member, domains):
    from approvals.models import ApprovalRequest
    return ApprovalRequest.objects.filter(company_id=member.company_id, document_type__in=['sales_order' if domain == 'sales' else 'purchase_order' for domain in domains])


def overdue_invoices(company_id):
    from invoicing.models import Invoice
    from invoicing.queries import invoice_balances
    return invoice_balances(Invoice.objects.filter(company_id=company_id, status='validated', due_date__lt=timezone.localdate())).filter(outstanding__gt=0)


def visible(member):
    permissions, modules, domains = sources(member)
    clause = Q(pk__in=[])
    if domains:
        requests = requests_for(member, domains)
        if 'approvals.requests.view' in permissions and 'approvals.requests.decide' in permissions:
            roles = member.membershiprole_set.filter(company_id=member.company_id).values('role_id')
            clause |= Q(type='approval_request', approval_request_id__in=requests.filter(status='pending', approver_role_id__in=roles).values('id'))
        clause |= Q(type='approval_decision', approval_request_id__in=requests.filter(requested_by=member, decision__isnull=False).values('id'))
    if 'crm' in modules and 'crm.view' in permissions:
        clause |= Q(type='crm_due', crm_activity__assigned_to=member, crm_activity__status='planned', crm_activity__due_at__lte=timezone.now(), source_due_at=F('crm_activity__due_at'))
    if 'invoicing' in modules and 'invoicing.invoice.view' in permissions:
        clause |= Q(type='invoice_overdue', invoice_id__in=overdue_invoices(member.company_id).values('id'))
    return Notification.objects.filter(company_id=member.company_id, recipient=member).filter(clause)


@transaction.atomic
def sync(user, company_id):
    member = access(user, company_id, True)
    permissions, modules, domains = sources(member)
    events = []
    if domains:
        requests = requests_for(member, domains)
        if 'approvals.requests.view' in permissions and 'approvals.requests.decide' in permissions:
            roles = member.membershiprole_set.filter(company_id=company_id).values('role_id')
            for obj in requests.filter(status='pending', approver_role_id__in=roles):
                reference = obj.document_snapshot.get('reference', '')
                events.append(Notification(company_id=company_id, recipient=member, type='approval_request', event_key=f'approval-request:{obj.pk}', approval_request=obj, title=f'Approbation demandée : {reference}', message=f'Version {obj.document_version} en attente de votre rôle approbateur.'))
        for obj in requests.filter(requested_by=member, decision__isnull=False).select_related('decision'):
            decision = obj.decision
            events.append(Notification(company_id=company_id, recipient=member, type='approval_decision', event_key=f'approval-decision:{decision.pk}', approval_request=obj, title=f'Décision : {obj.document_snapshot.get("reference", "")}', message=f'La version {obj.document_version} a été {"approuvée" if decision.decision == "approved" else "rejetée"}.'))
    if 'crm' in modules and 'crm.view' in permissions:
        from crm.models import CRMActivity
        for obj in CRMActivity.objects.filter(company_id=company_id, assigned_to=member, status='planned', due_at__lte=timezone.now()).select_related('lead'):
            events.append(Notification(company_id=company_id, recipient=member, type='crm_due', event_key=f'crm-due:{obj.pk}:{obj.due_at.isoformat()}', crm_activity=obj, source_due_at=obj.due_at, title=f'Activité échue : {obj.lead.title}', message=obj.description))
    if 'invoicing' in modules and 'invoicing.invoice.view' in permissions:
        for obj in overdue_invoices(company_id):
            events.append(Notification(company_id=company_id, recipient=member, type='invoice_overdue', event_key=f'invoice-overdue:{obj.pk}', invoice=obj, title=f'Facture en retard : {obj.reference}', message=f'Échéance du {obj.due_date:%d/%m/%Y}. Consulter le solde actuel de la facture.'))
    existing = set(Notification.objects.filter(company_id=company_id, recipient=member, event_key__in=[obj.event_key for obj in events]).values_list('event_key', flat=True))
    pending = [obj for obj in events if obj.event_key not in existing]
    Notification.objects.bulk_create(pending, ignore_conflicts=True, batch_size=500)
    return len(pending)


def data(obj):
    if obj.approval_request_id:
        request = obj.approval_request
        target = 'approbations' if obj.type == 'approval_request' else f'{"ventes" if request.sales_order_id else "achats"}/{request.sales_order_id or request.purchase_order_id}'
    elif obj.crm_activity_id: target = f'crm/{obj.crm_activity.lead_id}'
    else: target = f'factures/{obj.invoice_id}'
    return {'id': obj.pk, 'type': obj.type, 'title': obj.title, 'message': obj.message, 'created_at': obj.created_at, 'read_at': obj.read_at, 'target': target}
