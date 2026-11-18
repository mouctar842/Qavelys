from django.db import migrations

PERMISSIONS = {
    'contacts.view': 'Consulter les clients et fournisseurs', 'contacts.manage': 'Gérer les clients et fournisseurs',
    'products.view': 'Consulter les produits', 'products.manage': 'Gérer les produits',
    'categories.view': 'Consulter les catégories', 'categories.manage': 'Gérer les catégories',
    'taxes.view': 'Consulter les taxes', 'taxes.manage': 'Gérer les taxes',
}


def seed(apps, schema_editor):
    Unit = apps.get_model('reference', 'UnitOfMeasure')
    for symbol, name, category in [('u', 'Unité', 'count'), ('kg', 'Kilogramme', 'mass'), ('g', 'Gramme', 'mass'), ('L', 'Litre', 'volume'), ('mL', 'Millilitre', 'volume'), ('m', 'Mètre', 'length'), ('h', 'Heure', 'time'), ('j', 'Jour', 'time')]:
        Unit.objects.get_or_create(symbol=symbol, defaults={'name': name, 'category': category})
    Permission = apps.get_model('core', 'Permission')
    Role = apps.get_model('core', 'Role')
    RolePermission = apps.get_model('core', 'RolePermission')
    for code, description in PERMISSIONS.items():
        permission, _ = Permission.objects.get_or_create(code=code, defaults={'description': description})
        for role in Role.objects.filter(is_system=True, name='Administrateur'):
            RolePermission.objects.get_or_create(role=role, permission=permission)
    Module = apps.get_model('core', 'Module')
    Module.objects.filter(code__in=['contacts', 'catalog']).update(status='available')


class Migration(migrations.Migration):
    dependencies = [('reference', '0001_initial')]
    operations = [
        migrations.RunSQL('''
            ALTER TABLE reference_productcategory ADD CONSTRAINT category_parent_company_fk
            FOREIGN KEY (parent_id, company_id) REFERENCES reference_productcategory (id, company_id) ON DELETE RESTRICT;
            ALTER TABLE reference_product ADD CONSTRAINT product_category_company_fk
            FOREIGN KEY (category_id, company_id) REFERENCES reference_productcategory (id, company_id) ON DELETE RESTRICT;
            ALTER TABLE reference_producttax ADD CONSTRAINT producttax_product_company_fk
            FOREIGN KEY (product_id, company_id) REFERENCES reference_product (id, company_id) ON DELETE RESTRICT;
            ALTER TABLE reference_producttax ADD CONSTRAINT producttax_tax_company_fk
            FOREIGN KEY (tax_id, company_id) REFERENCES reference_tax (id, company_id) ON DELETE RESTRICT;
            ALTER TABLE reference_productpricehistory ADD CONSTRAINT pricehistory_product_company_fk
            FOREIGN KEY (product_id, company_id) REFERENCES reference_product (id, company_id) ON DELETE RESTRICT;
        ''', '''
            ALTER TABLE reference_productcategory DROP CONSTRAINT category_parent_company_fk;
            ALTER TABLE reference_product DROP CONSTRAINT product_category_company_fk;
            ALTER TABLE reference_producttax DROP CONSTRAINT producttax_product_company_fk;
            ALTER TABLE reference_producttax DROP CONSTRAINT producttax_tax_company_fk;
            ALTER TABLE reference_productpricehistory DROP CONSTRAINT pricehistory_product_company_fk;
        '''),
        migrations.RunPython(seed, migrations.RunPython.noop),
    ]
