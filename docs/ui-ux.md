# Interface et navigation du noyau

Palette du cahier des charges, thème clair/sombre conservé localement, formulaires React Hook Form + Zod et validation serveur, messages d’erreur et chargement, interface responsive. Button local conforme au modèle composable shadcn (Slot/CVA), Tailwind. Navigation via React Router, accès serveur par TanStack Query. Chaque clé de cache métier contient l’entreprise. Pas de données de remplacement en cas d’erreur.

Pages actuelles : accueil public, inscription, connexion, vérification e-mail, création guidée d’entreprise, vue d’ensemble d’administration, fiche entreprise, collaborateurs, rôles et compte. Les routes et transitions sont documentées dans [navigation.md](navigation.md).

L’espace connecté dispose d’une barre latérale rétractable, d’un en-tête avec entreprise active et thème, et d’une navigation filtrée par permissions. Le contexte de société est porté par l’URL et mémorisé par compte ; il reste présent sur la page de profil. Le logo de l’espace connecté ramène à son administration. La déconnexion efface les caches et ouvre la connexion. Une session manquante renvoie au formulaire et permet de reprendre une page interne après connexion.

La page des collaborateurs affiche les données API réelles, recherche, filtre de statut, tri par nom, pagination côté interface et confirmation native de suspension. La fiche entreprise et les rôles sont en lecture ; leur édition complète reste à développer. Les pages inconnues et les refus d’accès sont explicites, les erreurs réseau permettent de réessayer.

Les modules métier, le lanceur complet, les notifications et les dashboards financiers suivront les modules réellement livrés. Aucun compteur commercial fictif ni entrée de module inopérante n’est présenté. La présentation du noyau ne constitue pas une livraison de la V1 ERP complète.
