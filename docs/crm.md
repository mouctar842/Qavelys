# CRM — contrat V1

Extension du 17 novembre 2026 : la fiche prospect client ouvre un devis prérempli et affiche les documents commerciaux liés, via les vraies API Ventes. Création atomique, permissions et rattachement conservés : voir `orders-approvals.md`. Les mentions de conversion devis restante ci-dessous décrivent l’état historique du premier lot.

Application `crm`, routes `/api/v1/companies/:id/crm/`. Adhésion active, module crm activé et permissions crm.view/crm.manage. Le module dépend des contacts. Propriétaire et responsable d’activité sont des adhésions de la même entreprise, et les nouveaux responsables doivent être actifs. FK composites vers partenaire, adhésion et prospect ; archivage/suppression physique non exposés.

Prospects/opportunités : titre, partenaire facultatif, propriétaire, revenu attendu Decimal(20,6) non négatif, probabilité entière 0–100. Étapes initiales `new`, `qualified`, `proposal`, `won`, `lost` (Nouveau, Qualifié, Proposition, Gagné, Perdu). Changement d’étape par action explicite, audité ; un mouvement Kanban persiste en base. Aucune modification automatique des revenus ni des documents commerciaux par déplacement d’une carte.

Activités : type call/email/meeting/task, échéance UTC, responsable, description ; planned → done ou cancelled. Validation répétée d’un même état sans duplication d’audit ; mutation d’une activité terminée refusée. Toutes les relations sont vérifiées côté serveur et sous verrou société pour les mutations.

Conversion client : le nom et les coordonnées sont saisis par l’utilisateur, pas inventés depuis le titre de l’opportunité. Création atomique d’un partenaire client et rattachement au prospect, sans doublon lors d’une répétition. Si un partenaire est déjà rattaché, il est conservé et son indicateur client est activé. Le raccordement à un devis sera ajouté avec le module Ventes et protégé par ses permissions et son activation.

API : leads/ (liste paginée, filtres étape/propriétaire/recherche, création), leads/:id/ (détail), leads/:id/update/, move/, convert-customer/, history/ ; activities/ (liste/création), activities/:id/update|complete|cancel/ ; lookups/ (noms et identifiants minimaux de partenaires et collaborateurs pour l’affectation).
# Validation du premier lot CRM

Prospects, édition, liste, Kanban persistant, activités planifiées/terminées/annulées, historique et conversion client sont reliés à PostgreSQL. Conversion client : `crm.manage` **et** `contacts.manage`, modules CRM et contacts actifs. Les montants restent des chaînes décimales. Les relations société sont contraintes en SQL ; aucune suppression métier.

Tests exécutés : 6 backend et 4 frontend concluants. La conversion vers devis reste à relier au lot Ventes ; ce lot ne termine donc pas à lui seul tout le périmètre CRM V1.

