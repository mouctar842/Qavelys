from django.db import migrations

LINKS = [
    ('sales_salesorder', 'partner', 'reference_partner'), ('sales_salesorder', 'warehouse', 'inventory_warehouse'), ('sales_salesorder', 'lead', 'crm_lead'),
    ('sales_salesorderline', 'order', 'sales_salesorder'), ('sales_salesorderline', 'product', 'reference_product'),
    ('purchases_purchaseorder', 'partner', 'reference_partner'), ('purchases_purchaseorder', 'warehouse', 'inventory_warehouse'),
    ('purchases_purchaseorderline', 'order', 'purchases_purchaseorder'), ('purchases_purchaseorderline', 'product', 'reference_product'),
    ('inventory_stockreservation', 'sales_order_line', 'sales_salesorderline'), ('inventory_stockreservation', 'product', 'reference_product'), ('inventory_stockreservation', 'location', 'inventory_stocklocation'),
    ('approvals_approvalrule', 'approver_role', 'core_role'), ('approvals_approvalrequest', 'rule', 'approvals_approvalrule'), ('approvals_approvalrequest', 'approver_role', 'core_role'),
    ('approvals_approvalrequest', 'sales_order', 'sales_salesorder'), ('approvals_approvalrequest', 'purchase_order', 'purchases_purchaseorder'), ('approvals_approvalrequest', 'requested_by', 'core_membership'),
    ('approvals_approvaldecision', 'request', 'approvals_approvalrequest'), ('approvals_approvaldecision', 'approver_membership', 'core_membership'),
]


def seed(apps, schema_editor):
    Permission = apps.get_model('core', 'Permission'); RolePermission = apps.get_model('core', 'RolePermission'); Role = apps.get_model('core', 'Role')
    descriptions = {'approvals.rules.view': 'Consulter les règles d’approbation', 'approvals.rules.manage': 'Gérer les règles d’approbation', 'approvals.requests.view': 'Consulter les demandes d’approbation', 'approvals.requests.decide': 'Approuver ou rejeter une demande', 'sales.order.reserve': 'Réserver le stock manquant des commandes'}
    for domain, label in [('sales', 'ventes'), ('purchases', 'achats')]:
        for action, description in [('view', 'Consulter'), ('create', 'Créer'), ('edit', 'Modifier'), ('submit', 'Soumettre à approbation'), ('confirm', 'Confirmer'), ('cancel', 'Annuler')]: descriptions[f'{domain}.order.{action}'] = f'{description} les documents de {label}'
    for code, description in descriptions.items():
        permission, _ = Permission.objects.get_or_create(code=code, defaults={'description': description})
        for role in Role.objects.filter(is_system=True, name='Administrateur'): RolePermission.objects.get_or_create(role=role, permission=permission)
    apps.get_model('core', 'Module').objects.filter(code__in=['sales', 'purchases']).update(status='available')


class Migration(migrations.Migration):
    dependencies = [('approvals', '0003_initial'), ('inventory', '0004_stockreservation_sales_order_line_and_more'), ('purchases', '0001_initial'), ('sales', '0001_initial')]
    operations = [migrations.RunSQL(
        f'ALTER TABLE {table} ADD CONSTRAINT trade_link_{index}_company_fk FOREIGN KEY ({field}_id, company_id) REFERENCES {target} (id, company_id) ON DELETE RESTRICT;',
        f'ALTER TABLE {table} DROP CONSTRAINT trade_link_{index}_company_fk;'
    ) for index, (table, field, target) in enumerate(LINKS)] + [migrations.RunPython(seed, migrations.RunPython.noop)]
