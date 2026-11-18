CORE_PERMISSIONS = {
    'company.view': 'Consulter l’entreprise', 'company.manage': 'Modifier les paramètres',
    'members.view': 'Consulter les membres', 'members.manage': 'Gérer les membres et invitations',
    'roles.view': 'Consulter les rôles', 'roles.manage': 'Gérer les rôles et permissions',
    'modules.view': 'Consulter les modules', 'modules.manage': 'Activer et désactiver les modules',
    'audit.view': 'Consulter le journal d’audit', 'sequences.view': 'Consulter les séquences',
}
MODULES = {
    'hr': ('Équipe et missions', 'Employés, départements et missions distincts des accès utilisateurs', 'available', ['core']),
    'core': ('Administration', 'Comptes, entreprises, accès et audit', 'available', []),
    'contacts': ('Contacts', 'Clients et fournisseurs', 'available', ['core']),
    'catalog': ('Catalogue', 'Produits, unités et taxes', 'available', ['core']),
    'crm': ('CRM', 'Prospects et activités', 'available', ['contacts']),
    'inventory': ('Inventaire', 'Entrepôts et mouvements de stock', 'available', ['catalog']),
    'sales': ('Ventes', 'Devis et commandes clients', 'available', ['contacts', 'catalog', 'inventory']),
    'purchases': ('Achats', 'Commandes fournisseur et réceptions', 'available', ['contacts', 'catalog', 'inventory']),
    'invoicing': ('Facturation', 'Factures, avoirs, paiements et allocations', 'available', ['contacts']),
    'dashboard': ('Tableau de bord', 'Indicateurs sur vos données', 'available', ['core']),
}
SEQUENCES = {'sales_order': 'CMD-', 'purchase_order': 'ACH-', 'delivery': 'LIV-', 'receipt': 'REC-', 'invoice': 'FAC-', 'credit_note': 'AV-', 'transfer': 'TRF-', 'adjustment': 'AJU-'}
SEQUENCES['payment'] = 'PAY-'

for kind, label in [('employee', 'les employés'), ('department', 'les départements'), ('mission', 'les missions')]:
    CORE_PERMISSIONS[f'hr.{kind}.view'] = f'Consulter {label}'
    CORE_PERMISSIONS[f'hr.{kind}.manage'] = f'Gérer {label}'

CORE_PERMISSIONS.update({
    'approvals.rules.view': 'Consulter les règles d’approbation', 'approvals.rules.manage': 'Gérer les règles d’approbation',
    'approvals.requests.view': 'Consulter les demandes d’approbation', 'approvals.requests.decide': 'Approuver ou rejeter une demande',
    'inventory.view': 'Consulter les stocks et entrepôts', 'inventory.warehouse.manage': 'Gérer les entrepôts et emplacements',
    'inventory.transfer.create': 'Créer des transferts', 'inventory.transfer.validate': 'Valider des transferts',
    'inventory.adjustment.create': 'Créer des ajustements', 'inventory.adjustment.validate': 'Valider des ajustements',
    'crm.view': 'Consulter le CRM', 'crm.manage': 'Gérer les prospects et activités',
    'contacts.view': 'Consulter les clients et fournisseurs', 'contacts.manage': 'Gérer les clients et fournisseurs',
    'products.view': 'Consulter les produits', 'products.manage': 'Gérer les produits',
    'categories.view': 'Consulter les catégories', 'categories.manage': 'Gérer les catégories',
    'taxes.view': 'Consulter les taxes', 'taxes.manage': 'Gérer les taxes',
})
for domain, label in [('sales', 'ventes'), ('purchases', 'achats')]:
    for action, description in [('view', 'Consulter'), ('create', 'Créer'), ('edit', 'Modifier'), ('submit', 'Soumettre à approbation'), ('confirm', 'Confirmer'), ('cancel', 'Annuler')]:
        CORE_PERMISSIONS[f'{domain}.order.{action}'] = f'{description} les documents de {label}'
CORE_PERMISSIONS['sales.order.reserve'] = 'Réserver le stock manquant des commandes'
for domain in ('sales', 'purchases'):
    CORE_PERMISSIONS[f'{domain}.order.complete'] = 'Clôturer les commandes intégralement exécutées'
    CORE_PERMISSIONS[f'{domain}.order.resume'] = 'Reprendre une commande clôturée avec motif'
CORE_PERMISSIONS['dashboard.view'] = 'Consulter le tableau de bord autorisé'
CORE_PERMISSIONS['notifications.view'] = 'Consulter et gérer ses notifications'
for action, label in [('view', 'Consulter les paiements'), ('create', 'Enregistrer les paiements'), ('validate', 'Valider les paiements'), ('cancel', 'Annuler un enregistrement de paiement'), ('allocate', 'Allouer les paiements'), ('reverse_allocation', 'Extourner les allocations')]:
    CORE_PERMISSIONS[f'invoicing.payment.{action}'] = label
CORE_PERMISSIONS['invoicing.document.export'] = 'Exporter les documents financiers PDF'
for kind, label in [('invoice', 'factures'), ('credit_note', 'avoirs')]:
    for action, verb in [('view', 'Consulter'), ('create', 'Créer'), ('validate', 'Valider'), ('cancel', 'Annuler')]:
        CORE_PERMISSIONS[f'invoicing.{kind}.{action}'] = f'{verb} les {label}'
for kind, label in [('delivery', 'livraisons'), ('receipt', 'réceptions')]:
    for action, verb in [('view', 'Consulter'), ('create', 'Créer'), ('validate', 'Valider'), ('cancel', 'Annuler')]:
        CORE_PERMISSIONS[f'inventory.{kind}.{action}'] = f'{verb} les {label}'
