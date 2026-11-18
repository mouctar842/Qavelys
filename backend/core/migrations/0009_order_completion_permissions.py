from django.db import migrations


def grant(apps, schema_editor):
    Permission = apps.get_model('core', 'Permission')
    Role = apps.get_model('core', 'Role')
    RolePermission = apps.get_model('core', 'RolePermission')
    for domain in ('sales', 'purchases'):
        for action, label in [('complete', 'Clôturer les commandes intégralement exécutées'), ('resume', 'Reprendre une commande clôturée avec motif')]:
            permission, _ = Permission.objects.get_or_create(code=f'{domain}.order.{action}', defaults={'description': label})
            for role in Role.objects.filter(is_system=True, name='Administrateur'):
                RolePermission.objects.get_or_create(role=role, permission=permission)


class Migration(migrations.Migration):
    dependencies = [('core', '0008_logo_tenant_integrity')]
    operations = [migrations.RunPython(grant, migrations.RunPython.noop)]
