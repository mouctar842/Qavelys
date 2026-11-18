from django.db import migrations

LINKS = [('invoicing_payment', 'partner', 'reference_partner'), ('invoicing_paymentallocation', 'payment', 'invoicing_payment'), ('invoicing_paymentallocation', 'invoice', 'invoicing_invoice')]


def seed(apps, schema_editor):
    Permission = apps.get_model('core', 'Permission'); Role = apps.get_model('core', 'Role'); RolePermission = apps.get_model('core', 'RolePermission')
    labels = {'invoicing.document.export': 'Exporter les documents financiers PDF'}
    for action, label in [('view', 'Consulter les paiements'), ('create', 'Enregistrer les paiements'), ('validate', 'Valider les paiements'), ('cancel', 'Annuler un enregistrement de paiement'), ('allocate', 'Allouer les paiements'), ('reverse_allocation', 'Extourner les allocations')]: labels[f'invoicing.payment.{action}'] = label
    for code, description in labels.items():
        permission, _ = Permission.objects.get_or_create(code=code, defaults={'description': description})
        for role in Role.objects.filter(is_system=True, name='Administrateur'): RolePermission.objects.get_or_create(role=role, permission=permission)
    for company in apps.get_model('core', 'Company').objects.all(): apps.get_model('core', 'DocumentSequence').objects.get_or_create(company=company, document_type='payment', defaults={'prefix': 'PAY-'})
    apps.get_model('core', 'Module').objects.filter(code='invoicing').update(description='Factures, avoirs, paiements et allocations')


class Migration(migrations.Migration):
    dependencies = [('invoicing', '0003_payment_paymentallocation_and_more')]
    operations = [migrations.RunSQL(f'ALTER TABLE {table} ADD CONSTRAINT payment_{index}_company_fk FOREIGN KEY ({field}_id, company_id) REFERENCES {target} (id, company_id) ON DELETE RESTRICT;', f'ALTER TABLE {table} DROP CONSTRAINT payment_{index}_company_fk;') for index, (table, field, target) in enumerate(LINKS)] + [migrations.RunPython(seed, migrations.RunPython.noop)]
