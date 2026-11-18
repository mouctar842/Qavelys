from types import SimpleNamespace
from core.audit_presentation import present


def test_empty_partner_metadata_does_not_create_false_changes():
    entry = SimpleNamespace(action='partners.created', entity_type='Partner', before_data={}, after_data={'name': 'Client', 'customer_reference': '', 'supplier_reference': '', 'customer_notes': '', 'supplier_notes': '', 'delivery_address': ''})
    assert present(entry)['changes'] == [{'label': 'Nom', 'before': 'Non renseigné', 'after': 'Client'}]


def test_clearing_reference_and_adding_profile_still_show_changes():
    entry = SimpleNamespace(action='partners.updated', entity_type='Partner', before_data={'supplier_reference': 'REF-7', 'is_supplier': False}, after_data={'supplier_reference': '', 'is_supplier': True})
    changes = present(entry)['changes']
    assert {'label': 'Référence chez le fournisseur', 'before': 'REF-7', 'after': 'Non renseigné'} in changes
    assert {'label': 'Profil fournisseur', 'before': 'Non', 'after': 'Oui'} in changes
