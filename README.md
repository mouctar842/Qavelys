# Qavelys

ERP SaaS modulaire et multi-entreprises. Source officielle : [cahier des charges](QAVELYS_MASTER_SPEC.md). Développement progressif, sans données fictives ni modules simulés.

Le projet fournit le noyau SaaS, l’administration entreprise et plateforme, les logos fournis par entreprise, le référentiel, le CRM, les devis/commandes clients et fournisseurs, les approbations, les opérations de stock partielles, la facturation clients avec paiements/PDF, la clôture après règlement, le tableau de bord réel et les notifications personnelles, avec interfaces reliées à PostgreSQL. Les parcours ERP/clôture, logo et plateforme sont validés en E2E réel ; sondes de santé et sauvegarde/restauration locale sont testées. Durcissement et validation du déploiement production restent à finaliser. Consulter [la progression](docs/progress.md), [l’audit V1](docs/v1-acceptance-audit.md), [l’architecture](docs/architecture.md), [les contrats API](docs/api.md) et [les tests](docs/testing.md).

## Lancement local

1. Copier `.env.example` en `.env`, remplacer les valeurs de secrets.
2. Installer Docker Desktop avec Compose, ou PostgreSQL 17 et les outils Python/Node.
3. Docker : `docker compose up -d db`, puis `docker compose run --rm backend python manage.py migrate`, puis `docker compose up --build`.
4. Configurer le transport e-mail de développement selon [déploiement](docs/deployment.md), ouvrir http://localhost:5173, créer un compte, suivre le lien de vérification de l’e-mail local, se connecter, créer une entreprise.

Les instructions Windows sans Docker et les limites de production sont dans [déploiement](docs/deployment.md). Aucun compte administrateur ou secret par défaut n’est créé. Ne jamais supprimer le volume PostgreSQL sans accord explicite.

L’environnement Windows de cette session dispose déjà d’une instance PostgreSQL locale et d’un `.env` ignoré par Git ; voir [les accès locaux et résultats de tests](docs/progress.md). Vérification complète : `./infrastructure/verify.ps1`.

Tests navigateur réels : `./infrastructure/e2e.ps1`, avec Chromium installé par Playwright. Le lanceur crée une base PostgreSQL de test unique et utilise les ports 8001/5174. Rapports et données conservés, aucun nettoyage automatique ; voir [le contrat E2E](docs/e2e-acceptance.md) et [les écarts V1 restants](docs/v1-acceptance-audit.md).

Logo : importer le fichier de l’entreprise depuis **Paramètres → Logo de l’entreprise**. Administration globale : **/plateforme**, réservée au compte explicitement habilité ; voir [le contrat logo/plateforme](docs/platform-branding.md). Les droits plateforme n’accordent pas l’accès aux données métier d’une entreprise.

Dans cet environnement local, la vérification e-mail est temporairement désactivée à la demande de l’utilisateur. Une inscription avec une nouvelle adresse ouvre l’administration directement. Après création d’entreprise, activer les modules souhaités depuis « Modules » ; Contacts/Catalogue, CRM, Inventaire, Ventes, Achats, Facturation et Tableau de bord sont disponibles. La cloche de notifications appartient au noyau, selon les droits. Aucune donnée de démonstration n’est ajoutée aux entreprises.
