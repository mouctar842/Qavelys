# Architecture et dépendances

Monorepo : `backend/` Django/DRF, `frontend/` React strict/Vite, `infrastructure/`, `tests/`, `docs/`. API versionnée, monolithe modulaire, PostgreSQL exclusivement. Django 5.2 LTS ; versions exactes résolues dans les fichiers de verrouillage après installation.

Gunicorn est ajouté comme serveur WSGI Linux pour exécuter Django dans le conteneur, sans service applicatif supplémentaire. Nginx sert les fichiers compilés et conserve une origine unique pour les sessions et CSRF.

Ordre de réalisation :
1. Noyau comptes, sessions, entreprises, adhésions, RBAC, audit.
2. Onboarding complet, entrepôt initial, séquences, modules et dépendances ; référentiel contacts/produits/taxes/unités.
3. CRM → ventes ; référentiel → achats ; approbations communes avant confirmation.
4. Inventaire dépend de produits, entrepôts et documents sources ; réservations dépendent des ventes ; réceptions des achats ; livraisons des réservations.
5. Factures dépendent des contacts, taxes et éventuellement ventes ; allocations dépendent des factures/paiements/avoirs.
6. Dashboard agrège les documents réellement validés ; E2E traverse l’ensemble.

Les domaines futurs ne sont pas générés à vide. Aucun endpoint métier n’est exposé avant mise en place du contrôle module activé.

Décisions de réalisation du premier lot : origine unique par proxy Vite en développement et Nginx dans Compose, sessions côté serveur, aucun JWT ni stockage de session dans localStorage. Contexte entreprise explicite dans l’URL, jamais une sélection globale serveur partagée entre onglets. Réponses et cache identifiés par entreprise. Le superutilisateur plateforme ne contourne pas le RBAC métier.

Création d’entreprise transactionnelle et sérialisée par verrou utilisateur ; en-tête UUID `Idempotency-Key`, empreinte du contenu, réponse 200 lors d’une répétition identique et 400 si contenu différent. Les droits ne sont jamais acceptés dans le corps de création. Le rôle système Administrateur reçoit les permissions du noyau. Les permissions futures seront ajoutées par migration contrôlée.

La création du premier entrepôt, les séquences, le choix des modules et l’onboarding reprenable restent au lot suivant : la création d’espace actuelle ne signifie pas onboarding complet.
# Annuaire et missions

Espaces Clients/Fournisseurs : pages dédiées dans le routeur existant, Partner partagé et activité transversale en lecture dans `reference.partner_views`. Réutilisation des modèles CRM/commandes/logistique/finance et des requêtes `invoice_balances`, aucune comptabilité ou API de tiers parallèle. Anciens parcours /contacts conservés. Éditeurs existants alimentés par `usePartnerPrefill`, sans création de document à la consultation. Le graphique du dashboard est chargé dans un composant différé indépendant pour afficher les indicateurs/tableaux exacts avant la bibliothèque Recharts.

Extension métier autorisée par les sept chantiers : application Django `people`, module activable `hr` dépendant du noyau. Department/Employee/EmployeeMission réutilisent CompanyEntity et les mécanismes d’audit, transactions/verrous société, sessions/CSRF et permissions. Aucun système d’identité parallèle : Employee est une fiche professionnelle, éventuellement liée à Membership de la même entreprise. Ni création de compte ni attribution de rôles depuis les services RH. Frontend intégré aux routes existantes et au sélecteur avec caches par entreprise ; aucune refonte de stack. Contrat : `people.md`.

