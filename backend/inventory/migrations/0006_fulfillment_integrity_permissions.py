from django.db import migrations

LINKS = [
    ('inventory_delivery', 'sales_order', 'sales_salesorder'), ('inventory_delivery', 'location', 'inventory_stocklocation'),
    ('inventory_goodsreceipt', 'purchase_order', 'purchases_purchaseorder'), ('inventory_goodsreceipt', 'location', 'inventory_stocklocation'),
    ('inventory_deliveryline', 'document', 'inventory_delivery'), ('inventory_deliveryline', 'order_line', 'sales_salesorderline'),
    ('inventory_goodsreceiptline', 'document', 'inventory_goodsreceipt'), ('inventory_goodsreceiptline', 'order_line', 'purchases_purchaseorderline'),
    ('inventory_stockmovement', 'delivery_line', 'inventory_deliveryline'), ('inventory_stockmovement', 'receipt_line', 'inventory_goodsreceiptline'),
]


def seed(apps, schema_editor):
    Permission = apps.get_model('core', 'Permission'); Role = apps.get_model('core', 'Role'); RolePermission = apps.get_model('core', 'RolePermission')
    for kind, label in [('delivery', 'livraisons'), ('receipt', 'réceptions')]:
        for action, verb in [('view', 'Consulter'), ('create', 'Créer'), ('validate', 'Valider'), ('cancel', 'Annuler')]:
            permission, _ = Permission.objects.get_or_create(code=f'inventory.{kind}.{action}', defaults={'description': f'{verb} les {label}'})
            for role in Role.objects.filter(is_system=True, name='Administrateur'): RolePermission.objects.get_or_create(role=role, permission=permission)


class Migration(migrations.Migration):
    dependencies = [('inventory', '0005_delivery_deliveryline_goodsreceipt_goodsreceiptline_and_more'), ('approvals', '0005_approvalrequest_document_snapshot')]
    operations = [migrations.RunSQL(
        f'ALTER TABLE {table} ADD CONSTRAINT fulfillment_{index}_company_fk FOREIGN KEY ({field}_id, company_id) REFERENCES {target} (id, company_id) ON DELETE RESTRICT;',
        f'ALTER TABLE {table} DROP CONSTRAINT fulfillment_{index}_company_fk;'
    ) for index, (table, field, target) in enumerate(LINKS)] + [migrations.RunPython(seed, migrations.RunPython.noop)]
