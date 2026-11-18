# Logos fournis et administration plateforme

Sources : spécification 4, 6.1, 9 et 10 ; demande utilisateur du 17 novembre 2026. Pas de logo d’entreprise généré ou ajouté automatiquement. Le logo Qavelys conserve son rôle de navigation produit ; le logo importé identifie l’entreprise active dans la barre supérieure, sa fiche et ses paramètres.

## Logo privé par entreprise

POST multipart `companies/<id>/logo/`, champ `logo`, permission `company.manage`, session/CSRF et entreprise/adhésion actives. PNG, JPEG ou WebP décodables, une seule image, au plus 2 Mio et 4096 × 4096 pixels. Réencodage PNG sans métadonnées et taille ramenée à 1024 × 1024 maximum. SVG, animations, fichiers invalides et bombes de décompression refusés. Le nom client n’est jamais utilisé comme chemin.

Chaque import crée une version UUID immuable dans le stockage privé MEDIA_ROOT, puis modifie le pointeur `CompanySettings.logo`. Versions et fichiers précédents conservés : aucun bouton de suppression et aucun nettoyage automatique. En cas d’échec transactionnel après écriture, un fichier privé orphelin peut subsister, sans devenir accessible par l’API. Un remplacement conserve donc l’historique sans supprimer les données existantes.

GET `companies/<id>/logo/<logo_id>/` ne sert que la version courante, avec `company.view` et les contrôles habituels, Cache-Control private/no-store, Vary Cookie et nosniff. Aucun répertoire média public, URL distante ou accès plateforme contournant l’adhésion. `logo_url` nullable et versionnée est renvoyée dans les représentations Company/settings/context. Le frontend utilise un cache par société ; sans logo, afficher l’initiale de l’entreprise.

SQL : CompanyLogo UUID, FK company/uploaded_by PROTECT, fichier privé, taille/dimensions et empreinte SHA-256 ; unicité UUID/company. Settings.logo nullable PROTECT, FK composite (logo_id, company_id) → (id, company_id). Pas de suppression en cascade.

## Console plateforme séparée

Frontend `/plateforme`, API `/api/v1/platform/`. Accès uniquement à une session d’utilisateur actif avec `is_staff` ET `is_superuser`, vérification e-mail selon la politique existante et CSRF pour toute mutation. L’inscription publique ne peut jamais créer ces privilèges. `auth/me` expose seulement un booléen `is_platform_admin` calculé côté serveur. Les routes métier conservent leur contrôle d’adhésion ; aucun mode usurpation.

Vue d’ensemble et listes paginées/recherchables/triables : entreprises, utilisateurs, catalogue global des modules et journal plateforme. Données administratives seulement, sans factures, contacts ou stocks. Actions explicites suspend/activate pour une entreprise, deactivate/activate pour un utilisateur, avec motif de 8 à 1000 caractères et confirmation. Rejeu du même état sans nouvel audit ; aucune suppression. Interdiction de s’inactiver soi-même, de retirer le dernier super-administrateur actif ou de désactiver le dernier administrateur actif d’une société active. Une société suspendue conserve ses administrateurs et ses données ; sa réactivation exige toujours un administrateur actif.

Transactions PostgreSQL : verrou consultatif transactionnel commun aux mutations plateforme, relecture des privilèges de l’acteur, verrou utilisateur cible et entreprises concernées ordonnées pour les comptes ; verrou entreprise pour son statut. Les services normaux d’administration conservent leurs verrous société. Journal dédié PlatformAuditLog, FK acteur/cibles PROTECT, motif, avant/après et UTC ; aucune donnée secrète. Les droits plateforme ne sont pas modifiables depuis cette API.

Attribution initiale uniquement par commande opérateur `grant_platform_admin EMAIL` sur un compte existant actif, respectant la politique de vérification e-mail ; journalisée. Aucun compte ni mot de passe par défaut, aucune attribution automatique. Le rôle sera attribué au compte explicitement désigné par l’utilisateur.

## Acceptation

Tests PostgreSQL : images valides/invalides, limites, remplacement/historique, FK étrangère, accès étranger, rôle/module/adhésion/société, CSRF, stockage privé et en-têtes ; accès plateforme ordinaire/staff/seul superuser/inactif, listes sans secrets, statuts et rejouabilité, garde des administrateurs, audit et concurrence. Tests React : import/aperçu/erreur/changement société, navigation plateforme et refus, filtres/pagination/actions confirmées. Parcours navigateur réel sur base E2E séparée pour l’import et la console. Les limites non exécutées seront indiquées dans progress.md.
