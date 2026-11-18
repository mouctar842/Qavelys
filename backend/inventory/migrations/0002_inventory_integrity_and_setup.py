from django.db import migrations

LINKS = [
    ('stocklocation', 'warehouse', 'inventory_warehouse'),
    ('stockbalance', 'product', 'reference_product'), ('stockbalance', 'location', 'inventory_stocklocation'),
    ('stocktransfer', 'product', 'reference_product'), ('stocktransfer', 'source_location', 'inventory_stocklocation'), ('stocktransfer', 'destination_location', 'inventory_stocklocation'),
    ('stockadjustment', 'location', 'inventory_stocklocation'), ('stockadjustmentline', 'adjustment', 'inventory_stockadjustment'), ('stockadjustmentline', 'product', 'reference_product'),
    ('stockmovement', 'product', 'reference_product'), ('stockmovement', 'source_location', 'inventory_stocklocation'), ('stockmovement', 'destination_location', 'inventory_stocklocation'), ('stockmovement', 'transfer', 'inventory_stocktransfer'), ('stockmovement', 'adjustment_line', 'inventory_stockadjustmentline'),
]


def seed(apps, schema_editor):
    Permission = apps.get_model('core', 'Permission'); Role = apps.get_model('core', 'Role'); RolePermission = apps.get_model('core', 'RolePermission')
    Company = apps.get_model('core', 'Company'); Warehouse = apps.get_model('inventory', 'Warehouse'); Location = apps.get_model('inventory', 'StockLocation')
    for code, description in [('inventory.view', 'Consulter les stocks et entrepôts'), ('inventory.warehouse.manage', 'Gérer les entrepôts et emplacements'), ('inventory.transfer.create', 'Créer des transferts'), ('inventory.transfer.validate', 'Valider des transferts'), ('inventory.adjustment.create', 'Créer des ajustements'), ('inventory.adjustment.validate', 'Valider des ajustements')]:
        permission, _ = Permission.objects.get_or_create(code=code, defaults={'description': description})
        for role in Role.objects.filter(is_system=True, name='Administrateur'): RolePermission.objects.get_or_create(role=role, permission=permission)
    for company in Company.objects.iterator():
        warehouse, _ = Warehouse.objects.get_or_create(company=company, code='MAIN', defaults={'name': 'Entrepôt principal'})
        Location.objects.get_or_create(company=company, warehouse=warehouse, name='Stock', defaults={'type': 'internal'})
        for kind, name in [('customer', 'Clients'), ('supplier', 'Fournisseurs'), ('adjustment', 'Ajustements')]:
            Location.objects.get_or_create(company=company, warehouse=None, type=kind, defaults={'name': name})
    apps.get_model('core', 'Module').objects.filter(code='inventory').update(status='available')


class Migration(migrations.Migration):
    dependencies = [('inventory', '0001_initial'), ('reference', '0002_reference_integrity_and_catalog'), ('core', '0004_core_catalog_and_constraints')]
    operations = [migrations.RunSQL(
        f'ALTER TABLE inventory_{table} ADD CONSTRAINT inv_link_{index}_company_fk FOREIGN KEY ({field}_id, company_id) REFERENCES {target} (id, company_id) ON DELETE RESTRICT;',
        f'ALTER TABLE inventory_{table} DROP CONSTRAINT inv_link_{index}_company_fk;'
    ) for index, (table, field, target) in enumerate(LINKS)] + [migrations.RunPython(seed, migrations.RunPython.noop)]
