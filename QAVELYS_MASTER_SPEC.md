# Qavelys — Cahier des charges maître

**Version :** 1.0  
**Projet :** ERP SaaS généraliste, modulaire et multi-entreprises  
**Environnement :** VS Code + Codex  
**Objectif :** V1 fonctionnelle en environ 30 jours

> Ce document est la référence fonctionnelle et technique du projet. L'agent de développement doit le lire avant d'implémenter des fonctionnalités. Les décisions non encore spécifiées doivent être documentées et validées lorsqu'elles affectent les règles métier, la sécurité ou le périmètre.

## 1. Mission et vision

Construire **Qavelys**, un ERP web professionnel inspiré des principes d'Odoo, sans copier son identité. La plateforme permet à des entreprises de s'inscrire elles-mêmes, de créer leur espace, d'inviter leurs collaborateurs, d'activer leurs modules et de gérer CRM, ventes, achats, stocks, facturation, paiements, approbations et indicateurs. L'application doit être réelle, persistante, sécurisée, responsive et démontrable, et non une simple maquette.

### Principes non négociables

- Plusieurs entreprises par utilisateur, avec sélecteur d'entreprise.
- Isolation stricte des données et permissions par entreprise, vérifiée côté serveur.
- Modules activables par entreprise, sans destruction des données à la désactivation.
- RBAC : rôles et permissions propres à chaque entreprise.
- Une devise principale par entreprise et plusieurs entrepôts.
- Approbations configurables à un niveau pour la V1.
- Plusieurs factures par commande, livraisons et paiements partiels.
- Réservations de stock et prise en charge des quantités en attente de réapprovisionnement.
- Journal d'audit et tests automatisés des parcours critiques.
- Interface moderne dynamique avec thèmes clair et sombre.

## 2. Périmètre V1

| Domaine | Capacités obligatoires |
|---|---|
| SaaS | Inscription, vérification e-mail, connexion, réinitialisation, création d'entreprise, onboarding, invitations, sélecteur |
| Administration | Membres, rôles, permissions, modules, paramètres, séquences, audit |
| Référentiel | Clients/fournisseurs, produits/services, catégories, unités, taxes |
| CRM | Prospects, opportunités, étapes Kanban, activités, conversion vers devis |
| Ventes | Devis, confirmation, commandes, lignes, réservations, livraisons partielles |
| Achats | Fournisseurs, commandes d'achat, approbations, réceptions partielles |
| Inventaire | Entrepôts, emplacements, soldes, mouvements, réservations, transferts, ajustements |
| Facturation | Factures directes et issues de commandes, plusieurs factures, avoirs, paiements et allocations |
| Dashboard | KPI et graphiques calculés à partir des données réelles, filtres de période |

**Hors V1 :** RH, gestion de projets, comptabilité générale avancée, abonnements payants de la plateforme, moteur de workflow complexe, IA intégrée. Ne pas présenter la facturation comme une comptabilité complète.

## 3. Stack et architecture

- **Frontend :** React, TypeScript strict, Vite, Tailwind CSS, shadcn/ui, React Router, TanStack Query, React Hook Form, Zod, Recharts, Lucide.
- **Backend :** Python, Django, Django REST Framework, Django Auth et sessions sécurisées.
- **Données :** PostgreSQL, UUID pour les entités principales, UTC pour les dates, Decimal pour les montants.
- **Tests :** pytest/pytest-django, Vitest/Testing Library, Playwright.
- **Infrastructure :** Git, Docker Compose, configuration par variables d'environnement, HTTPS en production.
- **Style :** monolithe modulaire et API REST versionnée `/api/v1/`, frontend et backend dans un même dépôt.

Arborescence cible :

```text
qavelys/
├── frontend/
├── backend/
├── docs/
│   ├── master-spec.md
│   ├── architecture.md
│   ├── database.md
│   ├── business-rules.md
│   ├── ui-ux.md
│   ├── api.md
│   ├── testing.md
│   ├── deployment.md
│   └── progress.md
├── tests/
├── infrastructure/
├── AGENTS.md
├── README.md
├── .env.example
├── .gitignore
└── docker-compose.yml
```

Les secrets ne doivent jamais être versionnés. Les dépendances majeures supplémentaires nécessitent une justification.

## 4. SaaS, comptes et entreprises

### Onboarding

1. Création de compte : nom, e-mail, mot de passe.
2. Vérification de l'adresse e-mail.
3. Création de l'entreprise : nom, secteur, pays, devise, coordonnées.
4. Configuration : fuseau horaire, paramètres, premier entrepôt, rôles et séquences.
5. Activation des modules.
6. Accès au tableau de bord.

La création de l'entreprise et du premier administrateur doit être atomique et résistante aux requêtes répétées. Une entreprise conserve au moins un administrateur actif.

### Multi-entreprises

Un compte peut créer plusieurs entreprises ou rejoindre celles qui l'invitent. Le sélecteur change le contexte actif et recharge les droits, les modules et les données. Les caches frontend sont isolés par entreprise. Toute API métier vérifie le membership actif et la permission correspondante ; connaître un UUID ne suffit jamais à accéder à un objet.

### Invitations

Invitation par e-mail, avec jeton haché, date d'expiration, acceptation unique, révocation, renvoi et affectation de rôles. Prendre en charge les personnes déjà inscrites ou nouvelles.

### Administration

- **Super-administrateur plateforme :** gestion globale de Qavelys, séparée des parcours métiers.
- **Administrateur entreprise :** paramètres, utilisateurs, rôles, modules et approbations de sa société.
- **Employé :** accès limité à ses permissions.

## 5. Permissions et modules

Le modèle RBAC utilise `User`, `Company`, `Membership`, `Role`, `Permission`, `MembershipRole`, `RolePermission`. Un utilisateur peut avoir plusieurs rôles par entreprise. Les permissions sont granulaires (`sales.order.confirm`, `inventory.delivery.validate`, `invoicing.payment.create`, etc.). Les endpoints, exports, recherches et actions métier sont protégés côté serveur.

Les modules utilisent `Module`, `CompanyModule`, `ModuleDependency`. Désactiver un module bloque les nouvelles opérations et préserve l'historique. Les dépendances sont contrôlées avant activation ou désactivation. Le noyau SaaS reste toujours actif.

## 6. Modèle relationnel de référence

Les champs techniques communs (`id`, `created_at`, `updated_at`, auteur, etc.) sont ajoutés selon les besoins. Les tables métier portent `company_id` ; leurs relations doivent garantir l'appartenance à la même entreprise, y compris via contraintes composites lorsque nécessaire. Définir explicitement index, unicités, règles `ON DELETE` et transitions de statut avant migrations.

### 6.1 Noyau

| Entité | Champs essentiels / contraintes |
|---|---|
| `User` | id, email unique, password_hash, full_name, is_active, created_at |
| `Company` | id, name, slug unique, country_code, currency_code, sector, created_by, status |
| `Membership` | id, company_id, user_id, status, joined_at ; unique(company_id,user_id) |
| `Role` | id, company_id, name, is_system ; unique(company_id,name) |
| `Permission` | id, code unique, description |
| `MembershipRole` | membership_id, role_id ; rôle et membre de même société |
| `RolePermission` | role_id, permission_id |
| `Module` | id, code unique, name, description, status |
| `CompanyModule` | company_id, module_id, enabled, activated_at ; unique(company_id,module_id) |
| `ModuleDependency` | module_id, required_module_id |
| `CompanyInvitation` | id, company_id, email, token_hash, expires_at, accepted_at, revoked_at |
| `CompanySettings` | company_id, address, phone, logo, timezone, locale |
| Technique | Vérification e-mail, réinitialisation de mot de passe, onboarding |

### 6.2 Référentiel

| Entité | Champs essentiels |
|---|---|
| `Partner` | id, company_id, name, email, phone, address, is_customer, is_supplier, status |
| `Product` | id, company_id, sku, name, description, type, category_id, unit_id, sale_price, cost_price, active |
| `ProductCategory` | id, company_id, name, parent_id |
| `UnitOfMeasure` | id, name, symbol, category |
| `Tax` | id, company_id, name, rate, active |
| `ProductTax` | company_id, product_id, tax_id |
| `ProductPriceHistory` | Historique des modifications de prix, si requis |

`Product.type` : stockable, consommable, service. SKU unique par entreprise, mais réutilisable entre entreprises. Catalogue d'unités global et unité de référence par produit en V1. Un partenaire peut être client et fournisseur.

### 6.3 CRM et ventes

| Entité | Champs essentiels |
|---|---|
| `Lead` | id, company_id, partner_id nullable, title, stage, owner_id, expected_revenue, probability |
| `CRMActivity` | id, company_id, lead_id, assigned_to, type, due_at, status, description |
| `SalesOrder` | id, company_id, partner_id, lead_id nullable, reference, status, order_date, total_amount, created_by |
| `SalesOrderLine` | id, company_id, order_id, product_id, description, quantity, unit_price, discount_rate, tax_rate, line_total |
| `Delivery` | id, company_id, sales_order_id, reference, status, validated_at |
| `DeliveryLine` | id, company_id, delivery_id, sales_order_line_id, quantity |

Une commande confirmable possède au moins une ligne. Les prix et taxes sont figés sur les lignes de document. Séparer le statut de commande, le statut de livraison et le statut de facturation. Statuts de commande de référence : draft, pending_approval, confirmed, completed, cancelled.

### 6.4 Achats

| Entité | Champs essentiels |
|---|---|
| `PurchaseOrder` | id, company_id, supplier_id, reference, status, total_amount |
| `PurchaseOrderLine` | id, company_id, order_id, product_id, quantity, unit_cost, tax_rate |
| `GoodsReceipt` | id, company_id, purchase_order_id, warehouse_id, status, received_at |
| `GoodsReceiptLine` | id, company_id, receipt_id, purchase_line_id, quantity_received |

### 6.5 Inventaire

| Entité | Champs essentiels |
|---|---|
| `Warehouse` | id, company_id, name, code, active |
| `StockLocation` | id, company_id, warehouse_id nullable, name, type |
| `StockBalance` | company_id, product_id, location_id, quantity ; unique(company_id,product_id,location_id) |
| `StockReservation` | id, company_id, sales_order_line_id, product_id, location_id, quantity, status |
| `StockMovement` | id, company_id, product_id, source_location_id, destination_location_id, quantity, status, reference_type, reference_id, validated_at |
| `StockAdjustment` | id, company_id, location_id, status, reason |
| `StockAdjustmentLine` | id, company_id, adjustment_id, product_id, counted_quantity, difference |

Utiliser des emplacements internes et logiques (client, fournisseur, ajustement). Relier explicitement les mouvements aux documents sources lorsque l'intégrité référentielle le nécessite ; ne pas dépendre uniquement de références polymorphes non contrôlées.

### 6.6 Facturation et paiements

| Entité | Champs essentiels |
|---|---|
| `Invoice` | id, company_id, sales_order_id nullable, partner_id, reference, status, issue_date, due_date, total_amount |
| `InvoiceLine` | id, company_id, invoice_id, sales_order_line_id nullable, product_id nullable, description, quantity, unit_price, tax_rate, line_total |
| `Payment` | id, company_id, partner_id, amount, method, payment_date, external_reference |
| `PaymentAllocation` | id, company_id, payment_id, invoice_id, amount |
| `CreditNote` | id, company_id, invoice_id, reference, status, total_amount |
| `CreditNoteLine` | id, company_id, credit_note_id, invoice_line_id, quantity, amount |

Une commande peut produire plusieurs factures. Une facture issue d'une commande n'est liée qu'à une commande en V1. Factures directes possibles. Les paiements peuvent être partiels et ventilés sur plusieurs factures.

### 6.7 Approbations et transversal

| Entité | Champs essentiels |
|---|---|
| `ApprovalRule` | id, company_id, document_type, min_amount, max_amount, approver_role_id, active |
| `ApprovalRequest` | id, company_id, rule_id, document_type, document_id, document_version, status |
| `ApprovalDecision` | id, company_id, request_id, approver_membership_id, decision, comment, decided_at |
| `AuditLog` | id, company_id, actor_id, action, entity_type, entity_id, before_data, after_data, created_at |
| `Notification` | id, company_id, recipient_id, type, title, message, read_at, created_at |
| `DocumentSequence` | id, company_id, document_type, prefix, next_number |

Les séquences sont attribuées sans collision sous concurrence. Les approbations de la V1 comportent un seul niveau ; éviter les règles contradictoires. Les journaux n'exposent pas de secrets.

## 7. Cardinalités structurantes

- Company 1:N Membership ; User 1:N Membership.
- Membership N:N Role via MembershipRole ; Role N:N Permission via RolePermission.
- Company N:N Module via CompanyModule ; Module N:N Module via ModuleDependency.
- Company 1:N Partner, Product, Lead, Warehouse, SalesOrder, PurchaseOrder, Invoice.
- SalesOrder 1:N SalesOrderLine ; SalesOrder 1:N Delivery ; SalesOrder 1:N Invoice.
- PurchaseOrder 1:N PurchaseOrderLine et 1:N GoodsReceipt.
- GoodsReceipt 1:N GoodsReceiptLine ; SalesOrderLine 1:N DeliveryLine.
- Warehouse 1:N StockLocation ; Product et StockLocation N:N via StockBalance.
- SalesOrderLine 1:N StockReservation ; StockLocation 1:N StockReservation.
- Invoice 1:N InvoiceLine ; Payment N:N Invoice via PaymentAllocation.
- Invoice 1:N CreditNote ; ApprovalRule 1:N ApprovalRequest ; ApprovalRequest 1:N ApprovalDecision.

## 8. Règles métier et scénarios

### 8.1 Vente complète

Prospect → client → devis → éventuelle approbation → commande confirmée → réservation du stock disponible → attente de réapprovisionnement pour le manque → livraison partielle/totale → facture(s) → paiement(s) → dashboard.

- Prix et taux de taxe conservés sur les lignes après confirmation.
- Une modification significative d'un document approuvé requiert une nouvelle approbation.
- Les statuts sont validés par des transitions explicites côté backend.
- Une action répétée ne doit pas créer une double réservation, livraison ou facture.

### 8.2 Stocks

`stock_disponible = stock_physique - stock_réservé`.

Exemple : physique 50, déjà réservé 10, nouvelle commande 20 → nouvelle réservation 20, disponible 20. La réservation ne diminue pas le physique. La livraison de 20 diminue le physique de 20 et libère la réservation correspondante.

- Réservation par emplacement ; verrouillage transactionnel pour éviter la surréservation concurrente.
- Si la quantité demandée excède le disponible, réserver ce qui est disponible et conserver le solde en attente.
- Distinguer quantités commandées, réservées, en attente, livrées et facturées.
- Les produits de type service ne génèrent pas de mouvements de stock.
- Les réceptions augmentent le stock physique uniquement après validation.
- Les transferts internes diminuent une localisation et augmentent l'autre atomiquement, sans changer le stock total.
- Les ajustements produisent des mouvements traçables ; ne pas éditer directement les soldes sans historique.
- Empêcher les stocks disponibles négatifs et les doubles validations.

### 8.3 Achats

Commande fournisseur → approbation éventuelle → confirmation → une ou plusieurs réceptions → mouvements de stock. La somme des quantités reçues ne dépasse pas les quantités commandées, hors procédure de correction explicite.

### 8.4 Facturation

Une commande de 100 unités peut être facturée en 40 + 35 + 25 unités. Refuser une quantité cumulée excédant la commande, en tenant compte des avoirs validés. Une facture directe sans commande reste possible.

### 8.5 Paiements

Autoriser paiement complet/partiel, plusieurs paiements sur une facture et un paiement sur plusieurs factures. Ne pas allouer plus que le paiement disponible ni plus que le solde dû de chaque facture. Les soldes tiennent compte des paiements validés et des avoirs applicables.

### 8.6 Approbations

Règles par entreprise, type de document, intervalle de montant et rôle approbateur. Exemple configurable : achats supérieurs à 500 000 FCFA. Les opérations bloquées restent interdites avant approbation. Conserver l'auteur, la date, la décision et la version du document approuvé.

## 9. Design system et expérience utilisateur

**Style :** moderne, dynamique, professionnel, responsive, sans surcharge. **Thèmes :** clair et sombre, préférence conservée.

| Usage | Couleur |
|---|---|
| Primaire violet | `#6D5DF5` |
| Bleu | `#2563EB` |
| Turquoise | `#14B8A6` |
| Orange | `#F59E0B` |
| Bleu nuit | `#0F172A` |

Navigation : logo Qavelys, barre latérale rétractable, barre supérieure, sélecteur d'entreprise, recherche contextuelle, notifications, profil, choix de thème et lanceur d'applications. Menus filtrés par modules et permissions. Tables avec recherche, tri, filtres, pagination ; formulaires validés ; états de chargement, erreurs et listes vides ; confirmations pour actions sensibles. Aucun bouton fictif.

### 9.1 Pages publiques et onboarding

Accueil produit, inscription, connexion, vérification e-mail, mot de passe oublié/réinitialisation, création d'entreprise, configuration initiale, choix des modules et invitation de collaborateurs. Onboarding progressif et reprenable lorsque possible.

### 9.2 Accueil et dashboard

Lanceur d'applications et tableau de bord avec ventes facturées, commandes, clients, factures impayées, évolution des ventes, approbations en attente, alertes stock, retards de paiement et activités récentes. KPI réels, filtres de période, états vides explicites.

### 9.3 CRM

Liste prospects, Kanban par étape, fiche prospect, création/édition, activités, historique, conversion vers client et devis. Les déplacements Kanban persistent en base.

### 9.4 Ventes

Liste devis, formulaire, fiche devis, liste commandes, fiche commande, réservations, livraisons et factures liées. Actions selon statut : sauvegarder, soumettre, approuver/rejeter, confirmer, livrer, facturer, annuler selon règles.

### 9.5 Achats

Fournisseurs, commandes, formulaire, détails, approbations, réceptions et historique. Afficher quantités commandées, reçues et restantes.

### 9.6 Inventaire

Produits, fiche produit, entrepôts, emplacements, état des stocks, réservations, mouvements, transferts, ajustements, historique. Afficher stock physique/réservé/disponible et ventilation par entrepôt.

### 9.7 Facturation

Liste et fiche facture, formulaire, paiements, allocations, avoirs, export PDF. Distinguer statut documentaire (brouillon, validée, annulée) et état de paiement (non payé, partiel, payé, en retard).

### 9.8 Administration

Entreprise, collaborateurs, invitations, rôles, matrice de permissions, catalogue de modules, règles d'approbation, séquences, audit.

## 10. API, sécurité et intégrité

- API REST `/api/v1/` avec ressources des domaines et actions explicites (`confirm`, `approve`, `validate-delivery`, `record-payment`, etc.).
- Les actions sensibles ne doivent pas pouvoir être contournées par un PATCH générique.
- Sessions Django sécurisées, cookies `Secure` en production, `HttpOnly`, `SameSite` approprié, CSRF, gestion CORS si origines distinctes, HTTPS.
- Vérification e-mail, réinitialisation sécurisée et limitation des tentatives de connexion.
- Contrôle systématique : membership actif + permission + module activé + objet appartenant à l'entreprise + relations cohérentes.
- Ne jamais faire confiance à un `company_id` transmis par le client sans contrôle.
- Isolation des listes, recherches, exports, fichiers, agrégations et caches.
- Transactions atomiques et verrous pour création d'entreprise, confirmation, réservations, réceptions, livraisons, transferts, paiements et approbations.
- Contraintes d'unicité pour références et séquences documentaires.
- Pas de secrets dans Git, logs ou réponses API.
- Traces d'audit pour les changements de droits, modules, validations, mouvements et paiements.

## 11. Tests et critères d'acceptation

**Tests backend :** auth, création d'entreprise, multi-membership, refus d'accès cross-tenant par ID, rôles, suspension, dernier administrateur, activation de modules, dépendances, validations de documents, calculs monétaires, stocks concurrents, doubles validations, réceptions partielles, facturation multiple, paiements partiels, avoirs, approbations et audit.

**Tests frontend :** navigation, thèmes, formulaires, erreurs, listes, sélecteur d'entreprise, permissions et états vides.

**Test end-to-end obligatoire :** inscription → création entreprise → modules → client → produit → entrepôt → réception → devis → confirmation → réservation → livraison → facture → paiement → vérification soldes → dashboard.

Tester aussi le changement entre deux entreprises avec données différentes, l'accès à des UUID d'une autre société, la désactivation d'un module et les opérations concurrentes. Ne jamais déclarer un test réussi sans l'avoir exécuté.

## 12. Déploiement et exploitation

Développement local, environnement de test et production. Docker Compose pour PostgreSQL, Django, frontend/proxy selon architecture retenue. HTTPS, migrations, fichiers statiques et médias, sauvegardes et restauration PostgreSQL, journaux, healthchecks et configuration de production. Ne pas exposer PostgreSQL publiquement ni activer `DEBUG` en production. Conserver une démonstration locale de secours et prévoir un déploiement accessible par navigateur.

## 13. Calendrier cible (30 jours)

| Période | Livraison |
|---|---|
| J1–J4 | Dépôt, architecture, PostgreSQL, auth, entreprises, memberships, RBAC |
| J5–J10 | Design system, thèmes, navigation, onboarding, modules, contacts, produits |
| J11–J16 | CRM, devis, commandes, achats, tests métiers initiaux |
| J17–J23 | Réservations, réceptions, livraisons, transferts, factures, paiements, approbations |
| J24–J30 | Dashboard, tests E2E, corrections, sécurité, Docker, documentation, démo |

Calendrier ambitieux : privilégier un parcours de bout en bout fiable plutôt que des fonctionnalités superficielles. En cas de retard, réduire les options secondaires, pas la sécurité ni l'intégrité métier.

## 14. Instructions permanentes à Codex

1. Lire ce document avant de développer et le traiter comme source de vérité du périmètre V1.
2. Inspecter le dépôt avant modification ; ne pas écraser les fichiers existants sans justification.
3. Travailler par lots cohérents et petits, sans générer tout l'ERP en une seule intervention.
4. Pour chaque lot : annoncer le périmètre, implémenter, migrer si nécessaire, tester, corriger, documenter et résumer.
5. Demander validation pour les changements majeurs d'architecture, de sécurité, de périmètre ou de règles métier ; prendre les décisions techniques mineures raisonnables.
6. Éviter le code dupliqué, les mocks de production, les statistiques fictives, les boutons inertes et les raccourcis de sécurité.
7. Utiliser des données de démonstration uniquement si elles sont clairement identifiées et séparées des données réelles.
8. Documenter les contrats API, contraintes SQL, décisions d'arrondi, politiques d'annulation et comportements de suppression avant leur implémentation lorsqu'ils ne sont pas encore fixés.
9. Maintenir `docs/progress.md` avec réalisé, testé, restant, blocages et prochaines tâches.
10. À chaque jalon, rapporter les fichiers modifiés, les tests réellement exécutés et leurs résultats, ainsi que les limites connues.

## 15. Instruction de démarrage

**Commence maintenant le développement de Qavelys**, sans tenter de tout réaliser d'un coup :

1. Inspecte le dossier ouvert dans VS Code et les outils installés.
2. Propose puis établis l'arborescence du monorepo.
3. Initialise Git si nécessaire, sans écraser de travail existant.
4. Crée `AGENTS.md` et les documents techniques complémentaires.
5. Prépare Django/DRF, React/TypeScript et PostgreSQL.
6. Configure les variables d'environnement, Docker local et les premiers tests.
7. Implémente progressivement le noyau SaaS : User, Company, Membership, rôles et permissions.
8. Vérifie les migrations et tests, puis présente le bilan et le prochain lot.

**Qavelys doit devenir un ERP SaaS V1 réellement fonctionnel, pas une démonstration visuelle.**
