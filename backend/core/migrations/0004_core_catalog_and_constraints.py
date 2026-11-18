from django.db import migrations
from django.utils import timezone

PERMISSIONS = {
    'company.view': 'Consulter l’entreprise', 'company.manage': 'Modifier les paramètres',
    'members.view': 'Consulter les membres', 'members.manage': 'Gérer les membres et invitations',
    'roles.view': 'Consulter les rôles', 'roles.manage': 'Gérer les rôles et permissions',
    'modules.view': 'Consulter les modules', 'modules.manage': 'Activer et désactiver les modules',
    'audit.view': 'Consulter le journal d’audit', 'sequences.view': 'Consulter les séquences',
}
MODULES = {
    'core': ('Administration', 'Comptes, entreprises, accès et audit', []),
    'contacts': ('Contacts', 'Clients et fournisseurs', ['core']),
    'catalog': ('Catalogue', 'Produits, unités et taxes', ['core']),
    'crm': ('CRM', 'Prospects et activités', ['contacts']),
    'inventory': ('Inventaire', 'Entrepôts et mouvements de stock', ['catalog']),
    'sales': ('Ventes', 'Devis et commandes clients', ['contacts', 'catalog', 'inventory']),
    'purchases': ('Achats', 'Commandes fournisseur et réceptions', ['contacts', 'catalog', 'inventory']),
    'invoicing': ('Facturation', 'Factures, avoirs et paiements', ['contacts']),
    'dashboard': ('Tableau de bord', 'Indicateurs sur vos données', ['core']),
}


def seed(apps, schema_editor):
    Permission = apps.get_model('core', 'Permission')
    Role = apps.get_model('core', 'Role')
    RolePermission = apps.get_model('core', 'RolePermission')
    Module = apps.get_model('core', 'Module')
    ModuleDependency = apps.get_model('core', 'ModuleDependency')
    CompanyModule = apps.get_model('core', 'CompanyModule')
    DocumentSequence = apps.get_model('core', 'DocumentSequence')
    Company = apps.get_model('core', 'Company')
    for code, description in PERMISSIONS.items():
        permission, _ = Permission.objects.get_or_create(code=code, defaults={'description': description})
        for role in Role.objects.filter(is_system=True, name='Administrateur'):
            RolePermission.objects.get_or_create(role=role, permission=permission)
    modules = {}
    for code, (name, description, _) in MODULES.items():
        modules[code], _ = Module.objects.get_or_create(code=code, defaults={'name': name, 'description': description, 'status': 'available' if code == 'core' else 'planned'})
    for code, (_, _, dependencies) in MODULES.items():
        for dependency in dependencies:
            ModuleDependency.objects.get_or_create(module=modules[code], required_module=modules[dependency])
    sequences = {'sales_order': 'CMD-', 'purchase_order': 'ACH-', 'delivery': 'LIV-', 'receipt': 'REC-', 'invoice': 'FAC-', 'credit_note': 'AV-', 'transfer': 'TRF-', 'adjustment': 'AJU-'}
    for company in Company.objects.all().iterator():
        CompanyModule.objects.get_or_create(company=company, module=modules['core'], defaults={'enabled': True, 'activated_at': timezone.now()})
        for kind, prefix in sequences.items():
            DocumentSequence.objects.get_or_create(company=company, document_type=kind, defaults={'prefix': prefix})


class Migration(migrations.Migration):
    dependencies = [('core', '0003_auththrottle_module_companyinvitation_and_more')]
    operations = [
        migrations.RunSQL('''
            ALTER TABLE core_invitationrole ADD CONSTRAINT invitationrole_company_invitation_fk
            FOREIGN KEY (invitation_id, company_id) REFERENCES core_companyinvitation (id, company_id) ON DELETE CASCADE;
            ALTER TABLE core_invitationrole ADD CONSTRAINT invitationrole_company_role_fk
            FOREIGN KEY (role_id, company_id) REFERENCES core_role (id, company_id) ON DELETE RESTRICT;
        ''', '''
            ALTER TABLE core_invitationrole DROP CONSTRAINT invitationrole_company_invitation_fk;
            ALTER TABLE core_invitationrole DROP CONSTRAINT invitationrole_company_role_fk;
        '''),
        migrations.RunPython(seed, migrations.RunPython.noop),
    ]
