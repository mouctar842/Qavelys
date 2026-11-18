from django.db import migrations

LINKS = [('recipient', 'core_membership'), ('approval_request', 'approvals_approvalrequest'), ('crm_activity', 'crm_crmactivity'), ('invoice', 'invoicing_invoice')]


def seed(apps, schema_editor):
    Permission = apps.get_model('core', 'Permission'); Role = apps.get_model('core', 'Role'); RolePermission = apps.get_model('core', 'RolePermission')
    for code, description in [('dashboard.view', 'Consulter le tableau de bord autorisé'), ('notifications.view', 'Consulter et gérer ses notifications')]:
        permission, _ = Permission.objects.get_or_create(code=code, defaults={'description': description})
        for role in Role.objects.filter(is_system=True, name='Administrateur'): RolePermission.objects.get_or_create(role=role, permission=permission)
    apps.get_model('core', 'Module').objects.filter(code='dashboard').update(status='available')


class Migration(migrations.Migration):
    dependencies = [('core', '0005_notification'), ('crm', '0003_crmactivity_crm_activity_id_company_uq')]
    operations = [migrations.RunSQL(f'ALTER TABLE core_notification ADD CONSTRAINT notification_{field}_company_fk FOREIGN KEY ({field}_id, company_id) REFERENCES {table} (id, company_id) ON DELETE RESTRICT;', f'ALTER TABLE core_notification DROP CONSTRAINT notification_{field}_company_fk;') for field, table in LINKS] + [migrations.RunPython(seed, migrations.RunPython.noop)]
