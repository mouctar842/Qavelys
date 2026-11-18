# Acceptation E2E réelle — contrat du lot

Source officielle : spécification 11. Playwright/Chromium teste l’application React et Django réellement reliée à PostgreSQL. Aucun `route.fulfill`, backend simulé ou SQLite. Comptes/sociétés/documents marqués E2E, exclusivement dans une base locale nouvelle `qavelys_e2e_<identifiant>`. La base utilisateur `qavelys`, ses serveurs 8000/5173 et ses données sont conservés.

Le lanceur charge les secrets locaux sans les afficher, refuse une cible PostgreSQL distante et crée une base unique sans réutilisation ni suppression. Clé Django de test indépendante, DEBUG local et exception de vérification e-mail maintenus, ports de test distincts (8001/5174 par défaut). Les processus de test sont créés/arrêtés par Playwright ; aucun processus utilisateur n’est tué. La base et les artefacts de chaque exécution sont conservés pour diagnostic, avec nom/documentation explicites. Pas de nettoyage destructif automatique.

Le test crée les données depuis les interfaces : inscription → entreprise administrée → modules → contact client/fournisseur → taxe/produit → entrepôt → commande fournisseur et réceptions partielles → devis/confirmation/réservation → livraisons partielles → factures multiples → paiements/allocations → vérification des soldes et du dashboard. Les réponses réelles et lectures API authentifiées peuvent vérifier les invariants ; elles ne remplacent pas les actions UI du scénario.

Vérifications complémentaires : PDF réellement téléchargé, thème clair/sombre et viewport mobile, changement entre deux entreprises avec données distinctes, refus d’UUID étranger, module désactivé et absence de CSRF. Le rejeu sans double effet et la concurrence restent couverts par les tests backend PostgreSQL. Les captures et traces restent dans `.local/e2e-runs/<id>` (ignoré Git), sans secret de production. Le mot de passe du compte de test n’est utilisable que dans cette base séparée et n’est pas une configuration par défaut de l’application.

Délais bornés sur l’environnement Windows local : assertions E2E 60 s, parcours complet 20 minutes maximum ; navigation par liens React lorsque disponibles, sans rechargement répété de la page Modules. Aucun délai fixe ni nouvelle tentative automatique transformant un échec en succès.

Une réussite E2E ne suffit pas à déclarer toute la V1 complète : l’audit de couverture et les vérifications de sécurité/exploitation restent à traiter. Les régressions trouvées pendant ce lot sont corrigées puis revérifiées, avec résultats effectivement exécutés dans `progress.md`.
