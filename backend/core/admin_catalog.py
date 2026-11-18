"""Présentation des catalogues existants ; aucune autorisation n’est créée ici."""
from .catalog import MODULES

PREFIX_MODULE = {'products': 'catalog', 'categories': 'catalog', 'taxes': 'catalog', 'partners': 'contacts',
                 'company': 'core', 'members': 'core', 'membership': 'core', 'role': 'core',
                 'roles': 'core', 'modules': 'core', 'module': 'core', 'invitation': 'core',
                 'audit': 'core', 'sequences': 'core', 'notifications': 'core'}


def module_for(code):
    prefix = code.split('.')[0]
    return PREFIX_MODULE.get(prefix, prefix if prefix in MODULES or prefix == 'approvals' else 'other')


def module_label(code, names=None):
    return (names or {}).get(code) or {'approvals': 'Approbations', 'other': 'Autres autorisations'}.get(code) or MODULES.get(code, (code,))[0]


SEQUENCE_INFO = {
    'sales_order': ('sales', 'Devis et commandes clients', 'Référence des documents de vente.'),
    'purchase_order': ('purchases', 'Commandes fournisseurs', 'Référence des commandes d’achat.'),
    'delivery': ('inventory', 'Livraisons clients', 'Référence des sorties livrées aux clients.'),
    'receipt': ('inventory', 'Réceptions fournisseurs', 'Référence des entrées reçues des fournisseurs.'),
    'invoice': ('invoicing', 'Factures clients', 'Référence des factures directes et issues de commandes.'),
    'credit_note': ('invoicing', 'Avoirs clients', 'Référence des corrections par avoir.'),
    'payment': ('invoicing', 'Paiements clients', 'Référence des paiements enregistrés.'),
    'transfer': ('inventory', 'Transferts de stock', 'Référence des transferts entre emplacements.'),
    'adjustment': ('inventory', 'Ajustements de stock', 'Référence des inventaires et corrections de stock.'),
}

# Sélections explicites : de nouveaux droits ne sont jamais accordés par un wildcard.
COMMON = {'company.view', 'modules.view', 'dashboard.view', 'notifications.view'}
TEMPLATES = {
    'hr': ('Responsable RH', COMMON | {'members.view', 'hr.employee.view', 'hr.employee.manage', 'hr.department.view', 'hr.department.manage', 'hr.mission.view', 'hr.mission.manage'}),
    'employee': ('Employé', COMMON),
    'sales': ('Commercial', COMMON | {'contacts.view', 'contacts.manage', 'products.view', 'categories.view', 'taxes.view', 'crm.view', 'crm.manage', 'sales.order.view', 'sales.order.create', 'sales.order.edit', 'sales.order.submit', 'invoicing.invoice.view'}),
    'purchases': ('Responsable des achats', COMMON | {'contacts.view', 'contacts.manage', 'products.view', 'categories.view', 'taxes.view', 'inventory.view', 'purchases.order.view', 'purchases.order.create', 'purchases.order.edit', 'purchases.order.submit', 'inventory.receipt.view', 'inventory.receipt.create'}),
    'stock': ('Gestionnaire de stock', COMMON | {'products.view', 'categories.view', 'inventory.view', 'inventory.warehouse.manage', 'inventory.transfer.create', 'inventory.transfer.validate', 'inventory.adjustment.create', 'inventory.adjustment.validate', 'inventory.delivery.view', 'inventory.delivery.create', 'inventory.delivery.validate', 'inventory.receipt.view', 'inventory.receipt.create', 'inventory.receipt.validate', 'sales.order.view', 'purchases.order.view'}),
    'accountant': ('Comptable', COMMON | {'contacts.view', 'products.view', 'taxes.view', 'sales.order.view', 'invoicing.invoice.view', 'invoicing.invoice.create', 'invoicing.invoice.validate', 'invoicing.credit_note.view', 'invoicing.credit_note.create', 'invoicing.credit_note.validate', 'invoicing.payment.view', 'invoicing.payment.create', 'invoicing.payment.validate', 'invoicing.payment.allocate', 'invoicing.document.export'}),
    'manager': ('Gestionnaire', COMMON | {'contacts.view', 'products.view', 'crm.view', 'sales.order.view', 'purchases.order.view', 'inventory.view', 'invoicing.invoice.view', 'invoicing.credit_note.view', 'invoicing.payment.view', 'approvals.requests.view'}),
}
