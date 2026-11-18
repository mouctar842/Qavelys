from django.db import migrations

LINKS = [
    ('invoicing_invoice', 'partner', 'reference_partner'), ('invoicing_invoice', 'sales_order', 'sales_salesorder'),
    ('invoicing_invoiceline', 'invoice', 'invoicing_invoice'), ('invoicing_invoiceline', 'product', 'reference_product'), ('invoicing_invoiceline', 'sales_order_line', 'sales_salesorderline'),
    ('invoicing_creditnote', 'invoice', 'invoicing_invoice'), ('invoicing_creditnoteline', 'credit_note', 'invoicing_creditnote'), ('invoicing_creditnoteline', 'invoice_line', 'invoicing_invoiceline'),
]


def seed(apps, schema_editor):
    Permission = apps.get_model('core', 'Permission'); Role = apps.get_model('core', 'Role'); RolePermission = apps.get_model('core', 'RolePermission')
    for kind, label in [('invoice', 'factures'), ('credit_note', 'avoirs')]:
        for action, verb in [('view', 'Consulter'), ('create', 'Créer'), ('validate', 'Valider'), ('cancel', 'Annuler')]:
            permission, _ = Permission.objects.get_or_create(code=f'invoicing.{kind}.{action}', defaults={'description': f'{verb} les {label}'})
            for role in Role.objects.filter(is_system=True, name='Administrateur'): RolePermission.objects.get_or_create(role=role, permission=permission)
    apps.get_model('core', 'Module').objects.filter(code='invoicing').update(status='available', description='Factures et avoirs clients ; paiements à venir')


class Migration(migrations.Migration):
    dependencies = [('invoicing', '0001_initial'), ('inventory', '0006_fulfillment_integrity_permissions')]
    operations = [migrations.RunSQL(
        f'ALTER TABLE {table} ADD CONSTRAINT finance_{index}_company_fk FOREIGN KEY ({field}_id, company_id) REFERENCES {target} (id, company_id) ON DELETE RESTRICT;',
        f'ALTER TABLE {table} DROP CONSTRAINT finance_{index}_company_fk;'
    ) for index, (table, field, target) in enumerate(LINKS)] + [migrations.RunPython(seed, migrations.RunPython.noop)]
