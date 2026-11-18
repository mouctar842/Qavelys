from django.db import migrations


def seed(apps, schema_editor):
    Module = apps.get_model('core', 'Module')
    module, _ = Module.objects.get_or_create(code='hr', defaults={'name': 'Équipe et missions', 'description': 'Employés, départements et missions distincts des accès utilisateurs', 'status': 'available'})
    core = Module.objects.get(code='core')
    apps.get_model('core', 'ModuleDependency').objects.get_or_create(module=module, required_module=core)
    Permission = apps.get_model('core', 'Permission')
    Role = apps.get_model('core', 'Role')
    RolePermission = apps.get_model('core', 'RolePermission')
    for kind, label in [('employee', 'les employés'), ('department', 'les départements'), ('mission', 'les missions')]:
        for action, verb in [('view', 'Consulter'), ('manage', 'Gérer')]:
            permission, _ = Permission.objects.get_or_create(code=f'hr.{kind}.{action}', defaults={'description': f'{verb} {label}'})
            for role in Role.objects.filter(is_system=True, name='Administrateur'):
                RolePermission.objects.get_or_create(role=role, permission=permission)


class Migration(migrations.Migration):
    dependencies = [('people', '0001_initial'), ('core', '0009_order_completion_permissions')]
    operations = [
        migrations.RunSQL('''
            ALTER TABLE people_employee ADD CONSTRAINT employee_department_company_fk
              FOREIGN KEY (department_id, company_id) REFERENCES people_department(id, company_id) ON DELETE RESTRICT;
            ALTER TABLE people_employee ADD CONSTRAINT employee_membership_company_fk
              FOREIGN KEY (membership_id, company_id) REFERENCES core_membership(id, company_id) ON DELETE RESTRICT;
            ALTER TABLE people_employeemission ADD CONSTRAINT mission_employee_company_fk
              FOREIGN KEY (employee_id, company_id) REFERENCES people_employee(id, company_id) ON DELETE RESTRICT;
        ''', '''
            ALTER TABLE people_employeemission DROP CONSTRAINT mission_employee_company_fk;
            ALTER TABLE people_employee DROP CONSTRAINT employee_membership_company_fk;
            ALTER TABLE people_employee DROP CONSTRAINT employee_department_company_fk;
        '''),
        migrations.RunPython(seed, migrations.RunPython.noop),
    ]
