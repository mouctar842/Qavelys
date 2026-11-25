# Déployer l’interface Qavelys sur Vercel

Configuration du 25 novembre 2026. Ce lot reprend uniquement la préparation Vercel demandée ; les sept chantiers restent suivis séparément. Aucun déploiement ni transfert de données réalisé.

## Périmètre

`frontend/vercel.json` déploie React/Vite et relaie `/api/*` vers un backend Django HTTPS existant. Les autres routes chargent `index.html`, y compris après actualisation d’une fiche. Les URL API restent relatives : sessions et CSRF passent par le domaine de l’interface. Aucun secret frontend, aucune désactivation CSRF/CORS, aucun cache partagé des réponses métier. Les secrets `.env` du poste ne sont pas transférés.

Ce fichier ne déploie pas Django, PostgreSQL, les médias privés, SMTP ou les tâches planifiées. Vercel prend aussi en charge Django, mais migrer ce backend en fonctions demande une préparation dédiée (stockage durable, connexions PostgreSQL, migrations, PDF et validation des parcours). Ne pas considérer le déploiement de l’interface comme celui de l’ERP complet.

## Prérequis backend

- Backend public HTTPS opérationnel, base PostgreSQL de production migrée, médias privés persistants et sauvegardes.
- `DJANGO_DEBUG=0`, secret distinct et vérification e-mail active avec transport réel. Ne pas utiliser le `.env` local de développement.
- `FRONTEND_URL=https://VOTRE-PROJET.vercel.app` pour les liens de vérification/réinitialisation.
- `DJANGO_ALLOWED_HOSTS` contient l’hôte réellement reçu par Django à travers le proxy. Configurer `CSRF_TRUSTED_ORIGINS` avec l’origine exacte de l’interface dans les paramètres de production Django : la configuration actuelle ne lit pas cette variable automatiquement. Ne pas autoriser toutes les origines.
- Le proxy HTTPS du backend doit être configuré selon son hébergeur pour éviter les boucles de redirection ; ne pas faire confiance indistinctement aux en-têtes clients.
- Conserver des cookies sans domaine forcé, Secure/HttpOnly et les contrôles de session existants. Vérifier réellement les cookies et les POST depuis Vercel avant d’ouvrir les inscriptions.

## Commandes PowerShell

Depuis le dossier du projet, remplacer l’URL d’exemple par celle du backend réel :

```powershell
Set-Location 'C:\Users\Lenovo\Desktop\Qavelys'
.\infrastructure\configure-vercel.ps1 -BackendOrigin 'https://VOTRE-BACKEND.example.org'
Set-Location frontend
npm.cmd ci
npm.cmd run build
npx.cmd vercel@latest login
npx.cmd vercel@latest
```

Pour la première association interactive : sélectionner son compte, créer/choisir le projet Qavelys et conserver le dossier courant `./` comme racine (déjà `frontend`). Laisser Vercel utiliser `vercel.json` et le framework Vite. Le premier déploiement est une prévisualisation : adapter aussi les origines CSRF du backend à cette URL exacte pour la tester.

Après configuration du domaine final et du backend, publier :

```powershell
npx.cmd vercel@latest --prod
```

Pour les mises à jour, depuis `frontend` :

```powershell
npm.cmd run build
npx.cmd vercel@latest --prod
```

Ne pas exécuter ces commandes avec `--cwd` à la racine du dépôt : le projet Vercel doit utiliser `frontend`. Aucun besoin d’envoyer `.env` ou le dossier `.local`. Les migrations restent une opération explicite sur le backend après sauvegarde, pas dans le build frontend.

## Vérification de la cible

```powershell
$site = 'https://VOTRE-PROJET.vercel.app'
Invoke-WebRequest -UseBasicParsing "$site/api/v1/health/ready/"
Invoke-WebRequest -UseBasicParsing "$site/connexion"
```

La sonde doit renvoyer le JSON sain du backend, jamais le HTML React. Vérifier ensuite en navigateur : connexion, cookies, action POST protégée par CSRF, changement d’entreprise, logo privé, facture PDF et refus d’accès aux données d’une autre société. Les anciens comptes locaux ne sont pas copiés automatiquement. Aucune validation distante n’a été réalisée par la création de ces fichiers.

Sources : [Vercel Rewrites](https://vercel.com/docs/routing/rewrites), [configuration vercel.json](https://vercel.com/docs/project-configuration/vercel-json), [runtime Python](https://vercel.com/docs/functions/runtimes/python).
