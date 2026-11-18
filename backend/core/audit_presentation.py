from .admin_catalog import module_for, module_label

ENTITIES = {'Company': 'Entreprise', 'CompanySettings': 'Paramètres de l’entreprise', 'Membership': 'Accès collaborateur', 'Role': 'Rôle', 'Module': 'Module', 'CompanyInvitation': 'Invitation', 'DocumentSequence': 'Numérotation', 'Partner': 'Client ou fournisseur', 'Product': 'Produit', 'ProductCategory': 'Catégorie', 'Tax': 'Taxe', 'Lead': 'Prospect', 'CRMActivity': 'Activité CRM', 'SalesOrder': 'Commande client', 'PurchaseOrder': 'Commande fournisseur', 'Delivery': 'Livraison', 'GoodsReceipt': 'Réception', 'StockReservation': 'Réservation de stock', 'StockTransfer': 'Transfert', 'StockAdjustment': 'Ajustement', 'Invoice': 'Facture', 'CreditNote': 'Avoir', 'Payment': 'Paiement', 'PaymentAllocation': 'Allocation de paiement', 'ApprovalRule': 'Règle d’approbation', 'ApprovalRequest': 'Demande d’approbation'}
NOUNS = {'order': 'Commande', 'lead': 'Prospect', 'activity': 'Activité', 'rule': 'Règle d’approbation', 'request': 'Demande d’approbation', 'stock': 'Stock', 'reservation': 'Réservation', 'document': 'Document', 'warehouses': 'Entrepôt', 'locations': 'Emplacement', 'transfers': 'Transfert', 'adjustments': 'Ajustement', 'invoice': 'Facture', 'credit_note': 'Avoir', 'payment': 'Paiement', 'allocation': 'Allocation', 'delivery': 'Livraison', 'receipt': 'Réception'}
VERBS = {'created': 'Création', 'updated': 'Modification', 'create': 'Création', 'edit': 'Modification', 'confirm': 'Confirmation', 'confirmed': 'Confirmation', 'submit': 'Soumission à approbation', 'submitted': 'Soumission à approbation', 'complete': 'Clôture', 'resume': 'Reprise', 'cancel': 'Annulation', 'cancelled': 'Annulation', 'validate': 'Validation', 'validated': 'Validation', 'archive': 'Archivage', 'restore': 'Réactivation', 'activated': 'Réactivation', 'suspended': 'Suspension', 'enabled': 'Activation', 'disabled': 'Désactivation', 'approved': 'Approbation', 'rejected': 'Rejet', 'approve': 'Approbation', 'reject': 'Rejet', 'resend': 'Renvoi', 'revoke': 'Révocation', 'accepted': 'Acceptation', 'quoted': 'Conversion en devis', 'converted_customer': 'Conversion en client', 'created_from_lead': 'Création depuis un prospect', 'logo_uploaded': 'Import du logo', 'roles_updated': 'Modification des rôles', 'settings_updated': 'Modification des paramètres', 'reserved': 'Réservation', 'released': 'Libération', 'consumed': 'Consommation', 'allocated': 'Allocation', 'reversed': 'Extourne', 'stage': 'Changement d’étape', 'done': 'Activité terminée'}
FIELDS = {'name': 'Nom', 'title': 'Intitulé', 'reference': 'Référence', 'status': 'Statut', 'prefix': 'Préfixe', 'phone': 'Téléphone', 'email': 'E-mail', 'address': 'Adresse', 'sector': 'Secteur', 'timezone': 'Fuseau horaire', 'locale': 'Langue', 'reason': 'Motif', 'comment': 'Commentaire', 'quantity': 'Quantité', 'quantity_added': 'Quantité ajoutée', 'amount': 'Montant', 'total_amount': 'Montant total', 'sale_price': 'Prix de vente', 'cost_price': 'Coût', 'active': 'Actif', 'is_customer': 'Profil client', 'is_supplier': 'Profil fournisseur', 'stage': 'Étape', 'probability': 'Probabilité', 'expected_revenue': 'Revenu attendu', 'description': 'Description', 'due_at': 'Échéance'}
VALUES = {'active': 'Actif', 'suspended': 'Suspendu', 'archived': 'Archivé', 'draft': 'Brouillon', 'confirmed': 'Confirmé', 'completed': 'Terminé', 'cancelled': 'Annulé', 'pending_approval': 'En attente d’approbation', 'validated': 'Validé', 'approved': 'Approuvé', 'rejected': 'Rejeté'}
ENTITIES.update({'Employee': 'Employé', 'Department': 'Département', 'EmployeeMission': 'Mission'})
NOUNS.update({'employee': 'Employé', 'department': 'Département', 'mission': 'Mission'})
FIELDS.update({'full_name': 'Nom complet', 'staff_code': 'Matricule', 'job_title': 'Poste', 'responsibilities': 'Responsabilités', 'department_name': 'Département', 'employee_name': 'Employé affecté', 'due_date': 'Échéance'})
FIELDS.update({'customer_reference': 'Référence client', 'supplier_reference': 'Référence chez le fournisseur', 'delivery_address': 'Adresse de livraison', 'customer_notes': 'Notes commerciales', 'supplier_notes': 'Notes d’approvisionnement'})
VALUES.update({'todo': 'À faire', 'in_progress': 'En cours', 'done': 'Terminée'})
VERBS.update({'start': 'Démarrage', 'reopen': 'Réouverture'})


def action_label(action, entity_type=''):
    prefix, _, operation = action.partition('.')
    noun = ENTITIES.get(entity_type, module_label(module_for(action)))
    verb = VERBS.get(operation)
    if verb is None:
        for key in sorted(VERBS, key=len, reverse=True):
            if operation.endswith('_' + key):
                verb = VERBS[key]
                noun = NOUNS.get(operation[:-(len(key) + 1)], noun)
                break
    return f'{verb or "Événement enregistré"} · {noun}'


def display(value):
    if value is None or value == '': return 'Non renseigné'
    if isinstance(value, bool): return 'Oui' if value else 'Non'
    return VALUES.get(str(value), str(value))


def present(entry, permission_names=None, role_names=None, member_names=None):
    before, after = entry.before_data, entry.after_data
    changes = [{'label': label, 'before': display(before.get(key)), 'after': display(after.get(key))}
               for key, label in FIELDS.items() if key in after and before.get(key) != after[key] and not isinstance(after[key], (dict, list)) and not (entry.entity_type == 'DocumentSequence' and key == 'name')]
    changes = [change for change in changes if change['before'] != change['after']]
    if entry.entity_type == 'Employee' and 'membership_id' in after and before.get('membership_id') != after['membership_id']:
        changes.append({'label': 'Lien vers un accès Qavelys',
                        'before': 'Accès lié' if before.get('membership_id') else 'Sans accès lié',
                        'after': ('Accès lié remplacé' if before.get('membership_id') else 'Accès lié') if after['membership_id'] else 'Sans accès lié'})
    for key, names, label in [('permissions', permission_names or {}, 'Autorisations'), ('roles', role_names or {}, 'Rôles')]:
        if key in after and before.get(key) != after[key]:
            def labels(values):
                return ', '.join(names.get(str(code), 'Élément historique indisponible') for code in values) or 'Aucun'
            changes.append({'label': label, 'before': labels(before.get(key, [])), 'after': labels(after[key])})
    target = next((str(data[key]) for data in (after, before) for key in ('reference', 'name', 'full_name', 'title', 'email') if data.get(key)), ENTITIES.get(entry.entity_type, 'Élément de l’entreprise'))
    if entry.entity_type == 'Membership':
        target = (member_names or {}).get(str(entry.entity_id), target)
    module = module_for(entry.action)
    return {'action_label': action_label(entry.action, entry.entity_type), 'target_label': target,
            'module_code': module, 'module_name': module_label(module), 'changes': changes}
