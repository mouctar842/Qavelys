from django.db import migrations


def seed(apps, schema_editor):
    Permission = apps.get_model('core', 'Permission')
    RolePermission = apps.get_model('core', 'RolePermission')
    Role = apps.get_model('core', 'Role')
    Module = apps.get_model('core', 'Module')
    for code, description in [('crm.view', 'Consulter le CRM'), ('crm.manage', 'Gérer les prospects et activités')]:
        permission, _ = Permission.objects.get_or_create(code=code, defaults={'description': description})
        for role in Role.objects.filter(is_system=True, name='Administrateur'):
            RolePermission.objects.get_or_create(role=role, permission=permission)
    Module.objects.filter(code='crm').update(status='available')


class Migration(migrations.Migration):
    dependencies = [('crm', '0001_initial')]
    operations = [migrations.RunSQL('''
        ALTER TABLE crm_lead ADD CONSTRAINT lead_partner_company_fk
        FOREIGN KEY (partner_id, company_id) REFERENCES reference_partner (id, company_id) ON DELETE RESTRICT;
        ALTER TABLE crm_lead ADD CONSTRAINT lead_owner_company_fk
        FOREIGN KEY (owner_id, company_id) REFERENCES core_membership (id, company_id) ON DELETE RESTRICT;
        ALTER TABLE crm_crmactivity ADD CONSTRAINT activity_lead_company_fk
        FOREIGN KEY (lead_id, company_id) REFERENCES crm_lead (id, company_id) ON DELETE RESTRICT;
        ALTER TABLE crm_crmactivity ADD CONSTRAINT activity_assignee_company_fk
        FOREIGN KEY (assigned_to_id, company_id) REFERENCES core_membership (id, company_id) ON DELETE RESTRICT;
    ''', '''
        ALTER TABLE crm_lead DROP CONSTRAINT lead_partner_company_fk;
        ALTER TABLE crm_lead DROP CONSTRAINT lead_owner_company_fk;
        ALTER TABLE crm_crmactivity DROP CONSTRAINT activity_lead_company_fk;
        ALTER TABLE crm_crmactivity DROP CONSTRAINT activity_assignee_company_fk;
    '''), migrations.RunPython(seed, migrations.RunPython.noop)]
