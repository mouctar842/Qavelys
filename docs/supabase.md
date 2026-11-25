# PostgreSQL Qavelys sur Supabase

Choix utilisateur du 25 novembre 2026 : Supabase remplace Neon comme hébergeur PostgreSQL. Django reste responsable des comptes, sessions, entreprises, rôles et opérations métier. React continue à appeler Django via `/api/v1/`. Aucune bibliothèque Supabase frontend, clé API publique, Supabase Auth ou nouvelle politique d’accès ne remplace les contrôles existants.

## Préparer le projet

Créer ou sélectionner un projet Supabase dédié Qavelys. Les projets connectés découverts à cette date sont tous inactifs ; aucune cible n’a été sélectionnée, restaurée ou modifiée automatiquement. Le mot de passe PostgreSQL n’est ni une clé anon ni une clé service_role : le conserver uniquement dans les secrets du backend.

Avant de migrer des tables métier dans `public`, **désactiver la Data API dans les paramètres du projet dédié** (aucun client Qavelys ne l’utilise). Vérifier aussi que `public` n’est pas exposé par GraphQL. Ne pas appliquer les migrations sur un projet partagé dont ces API doivent rester accessibles ; choisir alors un projet dédié ou préparer un schéma privé dans un lot explicite. Ne jamais exposer les tables métier sans RLS/politiques appropriées. L’isolation de cette architecture reste contrôlée par Django, pas par des politiques fondées sur Supabase Auth.

## Secrets à renseigner côté backend

Dans le bouton **Connect** du projet, copier les paramètres PostgreSQL exacts. Pour un serveur Django persistant sur IPv4, choisir **Session pooler**, port 5432. La connexion directe peut nécessiter IPv6. Ne pas déduire l’adresse du pooler à partir de la région.

```dotenv
POSTGRES_DB=postgres
POSTGRES_USER=postgres.REFERENCE_DU_PROJET
POSTGRES_PASSWORD=LE_MOT_DE_PASSE_POSTGRES
POSTGRES_HOST=HOTE_SESSION_POOLER_COPIE_DEPUIS_CONNECT
POSTGRES_PORT=5432
POSTGRES_SSLMODE=require
POSTGRES_TRANSACTION_POOLER=0
```

Pour vérifier aussi l’identité du serveur, télécharger le certificat CA depuis Supabase, le rendre disponible sur le serveur et utiliser `POSTGRES_SSLMODE=verify-full` et `POSTGRES_SSLROOTCERT=/chemin/ca.crt`. Le mode require impose le chiffrement mais n’est pas une garantie de vérification complète du nom du serveur.

Pour un futur backend serverless, le pooler transaction (paramètres fournis dans Connect, généralement port 6543) utilise `POSTGRES_TRANSACTION_POOLER=1` : curseurs serveur et préparation psycopg désactivés. Exécuter les migrations depuis une connexion directe ou session, pas depuis le pooler transaction. La durée de connexion Django reste nulle par défaut ; aucun pool Python ajouté.

## Commandes

### Script de création demandé

Fichier : `infrastructure/supabase-create-schema.sql`. Dans un **projet Supabase dédié vide**, ouvrir SQL Editor, coller le contenu et exécuter une seule fois. Supabase fournit déjà la base `postgres` : le script crée 67 tables, contraintes, index, séquences et sept catalogues techniques (historique des migrations compris), pas une nouvelle base PostgreSQL ni des comptes/entreprises. Il est transactionnel, refuse tout schéma public contenant déjà des tables et active RLS sans politique publique sur les tables créées. Le compte serveur Django doit disposer des droits appropriés ; aucun accès métier via Supabase Auth n’est prévu. Version source PostgreSQL 17, état de la sauvegarde du 25 novembre 2026 ; préférer les migrations Django pour les évolutions suivantes, ne jamais régénérer/relancer ce SQL sur une base existante.

**Pour le transfert complet demandé précédemment, ne pas exécuter ce script avant la restauration** : la restauration doit créer le schéma et importer les données ensemble. Ce script constitue une alternative d’initialisation vide ; il ne remplace pas la migration des données. Ne pas utiliser `migrate --fake` pour résoudre une collision. Après création vide, `python manage.py migrate --plan` contrôle les évolutions éventuelles du code.

### Transfert des données existantes (demande confirmée)

Une simple commande `migrate` ne transfère pas les données locales. La migration complète suit cet ordre : sauvegarde source privée avec médias ; sélection d’un projet actif dédié et contrôle de sa version PostgreSQL (source 17), espace disponible et API non exposées ; arrêt temporaire des écritures applicatives ; nouveau snapshot de transfert ; restauration du schéma applicatif `public` uniquement avec `pg_restore --no-owner --no-acl --single-transaction --exit-on-error` ; contrôle de toutes les tables/empreintes, UUID, contraintes FK, compteurs et migrations ; configuration du backend cible puis tests. Ne pas restaurer les schémas Supabase gérés (`auth`, `storage`, etc.) et ne jamais employer `--clean`, `DROP` ou écraser des objets existants. Si la cible contient déjà des objets applicatifs, suspendre l’import et examiner les collisions.

Les comptes métier Django sont transférés avec leurs mots de passe hachés, entreprises et rôles ; ce ne sont pas des utilisateurs Supabase Auth. Les médias doivent être copiés dans le stockage privé du backend avant bascule ; ils ne sont pas contenus dans PostgreSQL. Garder la base locale et les sauvegardes pour retour arrière. Ne pas basculer le `.env` du poste avant contrôle complet de la cible. Les commandes ci-dessous servent au contrôle/migrations de schéma, pas à l’import des données existantes.

Sur l’hébergeur du backend, une fois les secrets configurés, depuis `backend` :

```powershell
python manage.py check
python manage.py shell -c "from django.db import connection; c=connection.cursor(); c.execute('SELECT 1'); assert c.fetchone()[0] == 1; print('Connexion PostgreSQL OK')"
python manage.py migrate --plan
python manage.py migrate --noinput
python manage.py healthcheck
```

Les commandes `manage.py` lisent l’environnement du processus. Ne pas utiliser `infrastructure/backend.ps1` pour la cible distante : ce script recharge le `.env` local. Les migrations créent le schéma sur la cible ; elles ne transfèrent pas les comptes/données du poste. Un transfert éventuel demande sauvegarde, contrôle de la cible et restauration dédiée ; ne pas restaurer aveuglément une base locale par-dessus les schémas gérés par Supabase.

## Vercel et validation restante

Le fichier `frontend/vercel.json` reste identique : destination = URL HTTPS du **backend Django**, jamais URL du projet Supabase. Suivre `vercel.md`. Les fichiers/logo restent un stockage privé séparé ; sélectionner la base Supabase ne configure pas Supabase Storage.

À vérifier sur la cible avant ouverture : TLS, migrations/FK/verrous, accès API désactivé, santé, cookies/CSRF, droits/isolation, concurrence et sauvegarde/restauration. Aucune connexion distante ni migration Supabase n’est déclarée réussie tant qu’un projet actif et les secrets de connexion ne sont pas disponibles.

Sources : [connexion PostgreSQL](https://supabase.com/docs/guides/database/connecting-to-postgres), [sécurisation de la Data API](https://supabase.com/docs/guides/api/securing-your-api).
