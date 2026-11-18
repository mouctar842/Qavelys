# Navigation Qavelys — correction du 16 novembre 2026

Référence consultée : https://odoolites.vercel.app/ (pages publiques et références de routes des scripts publics). Accueil → /login ou /inscription ; formulaire d’inscription avec société et modules ; destination /admin référencée par les formulaires. La lecture anonyme de /admin redirige vers /login. Aucune session créée sur le service tiers, aucune page privée inspectée et aucune règle serveur de ce service déduite de son interface. Les RH et la fabrication de cette référence restent hors V1 Qavelys. Son identité et ses données d’illustration ne sont pas reprises.

Qavelys conserve son onboarding compte puis entreprise, les règles multi-entreprises et son backend existant. Le parcours est désormais explicite, dans un espace de travail avec navigation permanente :

| Route | Comportement |
|---|---|
| / | Accueil public, liens inscription et connexion |
| /register, /inscription | Création de compte ; session immédiate en mode local déjà autorisé |
| /login, /connexion | Connexion ; retour à une page interne demandée lorsque possible |
| /administration, /admin | Session requise ; ouverture de l’entreprise mémorisée pour ce compte, sinon première entreprise ; création si aucune |
| /administration/entreprise/nouvelle | Formulaire réel de création, rôle administrateur attribué côté serveur, ouverture du nouvel espace |
| /administration/entreprises/:id | Accueil de l’entreprise et accès aux pages autorisées |
| /administration/entreprises/:id/entreprise | Fiche entreprise en lecture |
| /administration/entreprises/:id/collaborateurs | Liste/recherche/pagination et suspension confirmée via API existante |
| /administration/entreprises/:id/roles | Rôles réels en lecture |
| /administration/compte | Compte connecté et accès à ses entreprises |

La sélection est dans l’URL, conservée au rechargement, et mémorisée par identifiant de compte. L’entreprise mémorisée est toujours vérifiée contre les adhésions actives renvoyées par le serveur. Un changement d’entreprise conserve la page uniquement si les permissions correspondantes sont présentes ; sinon un refus explicite est affiché, sans montrer les données précédentes. Chaque cache métier inclut l’entreprise. Les pages collaborateurs et rôles vérifient leurs permissions et le backend garde le dernier mot. Les pages inconnues affichent une vraie page introuvable.

Seules les pages fonctionnelles du noyau sont proposées. Les modules métier ne sont pas simulés et aucun KPI illustratif n’est ajouté. Le menu est rétractable, les thèmes restent conservés, les erreurs réseau proposent une nouvelle tentative. La suppression de la session mène à la connexion sans recharger artificiellement toute l’application.
