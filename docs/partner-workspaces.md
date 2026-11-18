# Espaces Clients et Fournisseurs

Lot du 18 novembre 2026, chantier 5 autorisé. Cahier maître relu. Partner reste le référentiel unique ; UUID, sociétés, relations, historiques et anciens liens `/contacts` sont conservés. Aucun regroupement automatique sur nom/e-mail (ces valeurs ne prouvent pas une identité unique).

## Données et profils

Coordonnées communes existantes inchangées : nom, e-mail, téléphone, adresse générale. Champs complémentaires facultatifs, vides pour les données existantes : référence client (80), référence attribuée par le fournisseur (80), adresse de livraison client (2000), notes commerciales client (2000), notes d’approvisionnement fournisseur (2000). Les notes et références sont des métadonnées ; elles ne modifient ni prix, taxes, échéances, arrondis ou documents validés. Pas de contrainte d’unicité nouvelle sur les noms/e-mails/références externes.

Migration additive avec défaut SQL vide conservé sur les cinq colonnes, pour permettre au serveur précédent d’insérer encore des contacts pendant le redémarrage. Aucun champ existant transformé ; migration 0003 non appliquée sur la base utilisateur au moment de sa préparation.

Routes frontend distinctes `/clients` et `/fournisseurs`, chacune avec liste, création, fiche et édition. Client : référence client, livraison et notes commerciales ; fournisseur : référence du fournisseur et instructions d’approvisionnement. Coordonnées communes modifiées visibles dans les deux espaces. Une édition contextualisée n’envoie jamais les champs ni le booléen du profil opposé, afin de les conserver.

Avant de créer, recherche dans tous les tiers de l’entreprise avec l’API existante. L’utilisateur peut réutiliser une fiche par ajout explicite du profil manquant : POST `reference/partners/{id}/profiles/`, `{profile: customer|supplier}`. Permission contacts.manage + contacts.view, module Contacts, société et adhésion actives, verrou société ; répétition sans double audit ni duplication. Tiers archivé : réactivation explicite via le mécanisme existant. Aucun profil retiré implicitement. Archivage porte sur le tiers commun et est présenté clairement comme tel.

## Activité réelle et permissions

GET `reference/partners/{id}/activity/?profile=customer|supplier&section=...&page=1` ; contacts.view + module Contacts, mêmes contrôles serveur que le référentiel. Profil absent ou UUID étranger : 404. Réponse private/no-store. Catalogue de sections calculé depuis les modules actifs et permissions réels ; section interdite : 403, aucune quantité/montant correspondant divulgué.

Client : opportunités CRM (crm.view), devis/commandes (sales.order.view), livraisons (inventory.delivery.view), factures (invoicing.invoice.view), paiements (invoicing.payment.view). Fournisseur : commandes (purchases.order.view), réceptions (inventory.receipt.view). Chaque section exige son module actif, est filtrée par société et tiers, triée par date/UUID et paginée à 25. Les créances et crédits clients ne sont calculés que si invoice.view + payment.view + credit_note.view et Facturation actif ; réutilisation de `invoice_balances`, Decimal, sommes séparées par devise, factures validées uniquement. Aucun nouveau calcul d’arrondi.

Les fiches relient aux documents réels et proposent les créations autorisées. Préremplissage contrôlé du tiers dans les éditeurs existants via `?partner=UUID`, avec lecture par l’API Contacts et contrôle de profil actif côté interface et validation finale côté serveur métier. Aucun document ni paiement créé par la seule consultation d’une fiche.

Factures/règlements fournisseurs et comptabilité générale ne sont pas disponibles dans le backend actuel. Aucun solde fournisseur, bouton fictif ou assimilation aux factures clients dans ce lot. Leur ajout nécessite un lot financier dédié ; cette limite reste ouverte dans le plan des sept chantiers.

## Vérifications

Migration additive, aucune donnée effacée. Tests PostgreSQL : conservation des champs opposés/relations, ajout de profil rejouable et concurrent, filtrage des documents, soldes réels après allocations/avoirs, droits/modules/CSRF/UUID étrangers. Frontend : formulaires distincts, tiers existant, doubles profils, navigation et refus ; caches par société et contexte de profil. E2E sur base séparée, avec captures clair/mobile sombre. Suites lourdes séquentielles pour éviter les dépassements observés précédemment. Résultats dans progress.md.
