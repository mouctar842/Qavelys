# API v1 — contrat noyau

Relations commerciales : le CRUD `reference/partners/` expose cinq métadonnées optionnelles et recherche aussi les références client/fournisseur. `kind=customer|supplier|all` (valeur invalide 400). POST `partners/{id}/profiles/` accepte uniquement `{profile: customer|supplier}`, exige contacts.view/manage + module Contacts et ajoute le profil sans duplicata ni double audit ; tiers archivé refusé. GET `partners/{id}/activity/?profile=...&section=...&page=...` retourne uniquement les sections sources autorisées et actives, données limitées à cette société/ce tiers, pagination de 25, réponses privées/no-store. Soldes clients par devise uniquement avec les trois droits financiers de consultation. Livraisons/réceptions portent source_order_id pour consultation dans leur commande. Détails et limites financières fournisseur dans `partner-workspaces.md`.

Collaborateurs RH : sous `companies/{id}/hr/`, GET/POST `employees|departments|missions/`, GET/POST `{resource}/{uuid}/`, POST employés/départements `{uuid}/archive|restore/`, missions `{uuid}/start|complete|cancel|reopen/` ; GET `lookups/`. Lecture exige `hr.{employee|department|mission}.view`, écriture exige aussi `.manage`, module hr et adhésion/société actives. Choisir une adhésion exige members.view ; aucun accès créé/attribué par ce lien. Création avec request_key UUID, rejeu 200 (201 initial), autre contenu même clé ou version périmée 409. Édition complète des champs autorisés, version attendue ; statuts/actions explicites et aucune suppression. Réponses private/no-store. Contrat et limites : `people.md`.

Complément administration : GET `permissions/` enrichi de `module_code/module_name` depuis le catalogue réel. GET/POST `role-templates/` : catalogue consultable avec roles.view, installation explicite avec roles.manage, idempotente par nom, sans attribution ou écrasement. GET `audit/` conserve les champs bruts et ajoute action/cible/modules/société/changements lisibles et options de filtres ; paramètres `search/module/actor/start/end/page`, dates UTC inclusives, audit.view et entreprise requises. GET `sequences/` ajoute label/description/module/preview/can_edit ; POST `sequences/{type}/` accepte uniquement `prefix`, exige company.manage + sequences.view et refuse après première émission. Aucun compteur libre, référence passée inchangée. Contrats : `seven-workstreams-plan.md`.

Tableau de bord : GET `companies/{id}/dashboard/?start=&end=`, sections réellement autorisées uniquement, sommes Decimal par devise, soldes/alertes actuels et flux par période. Notifications personnelles : GET `notifications/` (`state`, `search`, `page`), GET `notifications/summary/`, POST `notifications/sync/`, POST `notifications/{id}/read/` (`read: true|false`), POST `notifications/read-all/`. Aucun destinataire libre transmis par le client ; UUID étranger/invisible renvoie 404. Réponses privées/no-store. Détail des contrats et dépendances : `dashboard-notifications.md`.

Paiements : `companies/{id}/invoicing/payments/` (liste/création), `{id}/` (détail), `{id}/validate|cancel/`, `{id}/allocate/` (lot à clé UUID), `allocations/{id}/reverse/` (motif), `lookups/`, `{id}/invoices/` et `{id}/history/`. Allocation refusée si montant supérieur au disponible/dû, client/devise/société incohérents ou paiement/facture non validés. Montants strictement à la précision ISO, sans arrondi silencieux. Les factures exposent payé/dû/crédit et état de règlement, avec détail des allocations uniquement si payment.view. PDF : GET `invoices/{id}/pdf/` / `credit-notes/{id}/pdf/`, document validé et permission d’export ; réponse PDF privée/no-store. Contrat complet `payments-pdf.md`.

Facturation : `companies/{id}/invoicing/invoices/` et `credit-notes/` (GET liste/détail, POST création), POST `{id}/validate|cancel/`, GET `lookups/` (clients/produits réels ou commande source avec `?order=`) et `history/?invoice=`. Clés de création UUID et montants sous forme de chaînes exactes ; source de commande/version ou facture/ligne contrôlée côté serveur. Avoirs périmés après changement d’arrondi cumulé : 409. Contrat `invoicing.md`. Les commandes clients exposent quantités nettes facturées/facturables et statut de facturation séparé du livré. Paiements et PDF restent à ajouter.

Réceptions/livraisons : ressources `companies/{id}/inventory/receipts/` et `deliveries/`, GET liste paginée/filtrée et détail, POST création, POST `{id}/validate|cancel/`, GET `lookups/?order={uuid}`. Lignes référencées par UUID de la version confirmée, emplacement du même entrepôt et société, clé de création rejouable ; voir `fulfillment.md`. Les fiches commande exposent `fulfillment_status` et les quantités `fulfilled_quantity`/`remaining_quantity`, en plus des réservations et du manque physique. Aucun PATCH générique ni suppression.

Préfixe `/api/v1/`, JSON, sessions Django. Toutes les mutations demandent CSRF, y compris anonymes. Obtenir `csrfToken` via GET `auth/csrf/` puis envoyer `X-CSRFToken`. Les cookies sont transmis sur la même origine. Les routes utilisent un slash terminal.

| Méthode | Route | Contrat |
|---|---|---|
| POST | auth/register/ | full_name, email, password ; 202 générique, e-mail de vérification |
| POST | auth/verify-email/ | token ; 200 ou 400 expiré/utilisé |
| POST | auth/login/ | email, password ; 200, 400 identifiants invalides, 403 `email_not_verified` après mot de passe correct, ou 429 |
| POST | auth/logout/ | session fermée, 200 |
| GET | auth/me/ | compte connecté, 403 sinon |
| GET | companies/ | entreprises avec adhésion active uniquement |
| POST | companies/ | name, country_code, currency_code, sector facultatif ; Idempotency-Key UUID obligatoire ; 201/200 |
| GET | companies/{uuid}/context/ | company.view ; entreprise et permissions recalculées |
| GET | companies/{uuid}/members/ | members.view ; membres de cette entreprise |
| GET | companies/{uuid}/roles/ | roles.view ; rôles de cette entreprise |
| POST | companies/{uuid}/members/{uuid}/suspend/ | members.manage ; 400 dernier administrateur, 404 membre extérieur |

403 uniforme sans divulgation des données d’une entreprise inaccessible. Aucun PATCH générique sensible. Les extensions sont décrites dans `core-completion.md`, `reference.md`, `crm.md`, `inventory.md` et `orders-approvals.md`. Certaines listes de configuration (rôles/membres) restent non paginées côté serveur ; les listes métier, l’audit et les invitations ont leur pagination propre.

Commandes : `companies/{id}/{sales|purchases}/orders/`, détail `{id}/`, historique `{id}/history/`, actions POST `update|submit|confirm|reopen|cancel/` et `reserve/` pour les ventes. Création avec `request_key` UUID ; modifications/actions avec version attendue, réponse 409 si obsolète. Lookups métier `{sales|purchases}/lookups/`. Listes : recherche, statut, tri autorisé et pagination. Aucun endpoint de suppression, réception/livraison/facture non encore reliées dans ce lot.

Approbations : `companies/{id}/approvals/rules/`, POST `{rule_id}/update/`, rôles disponibles `lookups/`, demandes `requests/`, décision POST `requests/{id}/decide/` (`approved` ou `rejected`, commentaire). Décision réservée à un membre actif possédant à la fois la permission et le rôle approbateur. Types vente/achat explicites et références aux documents contrôlées par FK.

Inscription : la réponse 202 reste générique pour les adresses existantes. Son message précise le transport réel en développement (fichier local ou console), sans jeton. La connexion avec mot de passe correct et adresse non vérifiée ne consomme pas de tentative de mot de passe. La vérification valide réinitialise le compteur de connexion de ce compte, y compris s’il avait atteint sa limite. Un mot de passe erroné reste limité à 5 échecs sur 15 minutes.

Commande d’administration locale `resend_verification EMAIL` : envoie un nouveau lien via le transport configuré, sans activer le compte et sans afficher le jeton dans la sortie de commande. Refuse un compte déjà vérifié ou inactif. Endpoint public complémentaire `POST auth/resend-verification/`, protégé par preuve du mot de passe et limitation persistante.

Exception temporaire autorisée par l’utilisateur le 16 novembre 2026 : en local, `DJANGO_DEBUG=1` et `REQUIRE_EMAIL_VERIFICATION=0` permettent inscription, connexion et création d’entreprise sans vérification. L’inscription n’émet alors aucun e-mail et ouvre directement une session pour un nouveau compte. Les comptes conservent leur véritable indicateur `email_verified` pour une réactivation ultérieure. En dehors de DEBUG, la vérification reste obligatoire.

Parcours d’inscription immédiate demandé ensuite : dans ce mode local, un nouveau compte est connecté par session Django dès sa création (201, `authenticated: true`), puis le frontend ouvre `/administration`. Une adresse déjà inscrite ne crée pas de session à partir du formulaire d’inscription (202, `authenticated: false`) ; il faut utiliser la connexion. Lorsque la vérification est requise, l’inscription reste en attente, sans session. L’administration permet de créer l’entreprise ; seul ce service transactionnel attribue le rôle Administrateur de cette entreprise. Aucun privilège plateforme n’est attribué à l’inscription.
# Logos d’entreprise et administration plateforme

Contrat détaillé : `platform-branding.md`. `Company` dans les listes/contextes et les paramètres inclut `logo_url` nullable. Import multipart POST `/api/v1/companies/<id>/logo/`, champ unique logo, permission company.manage et CSRF. GET `/api/v1/companies/<id>/logo/<version_uuid>/` : company.view, version courante de la même société, image/png, private/no-store. URL opaque privée ; pas de média public ni de chemin de fichier dans les réponses.

Console séparée : `/api/v1/platform/overview/`, `companies/`, `users/`, `modules/`, `audit/`. Exige utilisateur actif staff ET superuser. Listes : search, page, page_size (1–100), ordering limité ; status active/suspended pour entreprises, active/inactive pour utilisateurs. Actions POST `companies/<id>/suspend/|activate/`, `users/<id>/deactivate/|activate/` avec reason de 8–1000 caractères. Session/CSRF, pas de PATCH de privilèges ni de suppression. Réponses administratives sans secrets ni documents ERP. Journal distinct des audits métier. Les APIs métier et fichiers exigent toujours l’adhésion/permission propre à l’entreprise.

# Clôture et sondes de santé

Commandes : `complete/` et `resume/` sous les routes sales/purchases orders existantes. `version` et `closure_version` obligatoires ; motif de 8–1000 caractères pour resume. `completed_at`, `closure_version` et `completion={eligible,reasons}` dans les fiches autorisées, selon `order-completion-proposal.md`. 403 pour droits/modules, 400 pour conditions métier, 409 pour version/cycle périmé. Aucune mutation financière ou de stock par ces actions.

GET `/api/v1/health/live/` et `ready/` : status ok/unavailable, 200/503 et no-store, aucun détail technique/secret. Live ne requiert pas PostgreSQL ; ready vérifie SELECT 1 et migrations. HTTPS de production inchangé. Commandes opérateur : healthcheck, backup_instance, restore_instance ; aucune route web de restauration.

# Erreurs de transport e-mail

`auth/register/` et `auth/resend-verification/` renvoient HTTP 503 avec `detail` générique si le transport échoue ; le compte/jeton nouvellement créé est annulé. Les invitations et leur renvoi renvoient aussi 503, sans invalider le lien précédent en cas d’échec. `auth/password-reset/` conserve HTTP 202 et le même corps pour compte absent, présent, limité ou panne d’envoi. Aucun secret de transport ni jeton dans une réponse. Contrat détaillé et limites : `mail-delivery.md`.

