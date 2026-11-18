# Santé et sauvegarde/restauration

Source : spécification 12. Opérations locales d’abord, sans déploiement externe ni suppression.

## Santé applicative

GET `/api/v1/health/live/` : processus HTTP disponible, sans requête métier. GET `/api/v1/health/ready/` : SELECT 1 PostgreSQL et absence de migrations en attente. Réponses minimales `status=ok|unavailable`, HTTP 200/503, no-store, aucun nom de serveur, schéma, compte ou exception renvoyé. Les erreurs détaillées ne sont pas exposées. HTTPS reste obligatoire hors DEBUG comme pour le reste des routes.

Commande opérateur `healthcheck` réutilisant les contrôles de readiness, code 0/1. Compose l’utilise pour le backend sans devoir contourner HTTPS sur une requête loopback. Volume médias privé initialisé au propriétaire applicatif dans l’image. Docker reste à exécuter sur un poste équipé.

## Sauvegardes privées

Commande `backup_instance` : pg_dump format custom, schéma/données/séquences/contraintes, puis archive des médias immuables et manifeste SHA-256. Fichiers uniquement sous `.local/backups/<id>` (ignoré Git), accès propriétaire/SYSTEM sous Windows et propriétaire seul sous POSIX. Aucun secret de configuration ni `.env` dans l’archive. Le dump contient les données privées de l’application : ne pas le publier. La sauvegarde du cluster/roles, le chiffrement hors site et l’automatisation planifiée restent des sujets d’exploitation distincts.

Snapshot DB avant copie des médias : les fichiers de logos sont écrits avant leur référence transactionnelle et leurs versions ne sont pas supprimées ; tout média référencé par le snapshot existe donc déjà. Les fichiers restent immuables pendant la copie. La sauvegarde échoue si un média référencé est absent ou si une empreinte est invalide. Les fichiers supplémentaires créés après snapshot ne remplacent aucune donnée sauvegardée.

Depuis la racine Windows : `./infrastructure/backend.ps1 backup_instance`, puis `./infrastructure/backend.ps1 restore_instance CHEMIN_DU_DOSSIER`. Le rôle PostgreSQL doit disposer de CREATEDB pour le clone et de lecture de la source. Les clients PostgreSQL compatibles doivent être installés (outils 17.12 locaux disponibles sur ce poste). Aucun service applicatif ne bascule vers la cible. Vérifier le code versionné et les migrations avant toute future bascule manuelle. Les rapports `verified.json` restent dans le dossier privé du clone. Les empreintes de contenu concernent le schéma applicatif partagé public ; les rôles et objets globaux du cluster ne sont pas inclus.

Restauration `restore_instance DOSSIER` uniquement depuis une sauvegarde créée localement par cet outil, après validation du manifeste/dump/médias et de leurs empreintes. Cible PostgreSQL loopback dans une **nouvelle** base `qavelys_restore_<id>` et nouveaux médias `.local/restores/<id>/media`, jamais la base configurée ni un dossier existant. Refus avant mutation pour un nom non conforme, une base existante, une archive corrompue ou un chemin média dangereux. Pas de --clean, --create ou DROP côté pg_restore ; --exit-on-error et restauration atomique. En cas d’échec après création, cible de diagnostic conservée, jamais suppression automatique.

Vérification après restauration : contraintes FK validées, migrations et empreintes/contenu de toutes les tables comparés au snapshot, mêmes séquences et compteurs ne précédant aucune clé restaurée, médias référencés présents et SHA identiques. Les séquences PostgreSQL ne sont pas MVCC : leur valeur observée après le dump est informative, pas un état de snapshot à comparer strictement sous écritures concurrentes. Pas de serveur automatiquement démarré sur le clone ; les sessions copiées ne sont pas utilisées. Aucun secret Django n’est copié : configurer une clé indépendante avant toute utilisation applicative d’un clone.

Les outils restaurent du SQL privilégié et doivent traiter seulement des sauvegardes de confiance : [pg_dump PostgreSQL 17](https://www.postgresql.org/docs/17/app-pgdump.html), [pg_restore PostgreSQL 17](https://www.postgresql.org/docs/17/app-pgrestore.html). Le format custom et les contrôles d’empreinte détectent les altérations, sans prouver l’authenticité d’une archive fournie par un tiers.
