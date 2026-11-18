# Plan de réalisation de la V1

État initial du 16 novembre 2026 : noyau SaaS et navigation réels mais partiels ; aucun module métier encore implémenté. Le projet ne peut pas être présenté comme terminé à ce stade.

Ordre de travail, chaque lot migré/testé avant le suivant :
1. Noyau : réinitialisation et renvoi e-mail, profil/paramètres, invitations, rôles/permissions, activation des modules, audit et séquences.
2. Référentiel : contacts, produits/services, unités, catégories, taxes ; premier entrepôt et onboarding.
3. CRM : pipeline et activités, conversion vers partenaire/devis.
4. Ventes et achats : documents, lignes, transitions, approbations, prix/taxes figés.
5. Inventaire : emplacements, mouvements, réservations, réceptions/livraisons partielles, transferts et ajustements sous verrous.
6. Facturation : factures multiples/directes, avoirs, paiements et allocations, PDF.
7. Tableau de bord réel, notifications, E2E Playwright complet, tests de concurrence, durcissement, Docker et exploitation.

Décision financière validée par l’utilisateur : arrondi au total de la facture, sans arrondi intermédiaire de ligne. Application partagée dans `core.money` et détail dans `financial-policy-proposal.md` ; conserver cette règle pour les prochains documents.

État au 17 novembre 2026 : noyau, référentiel et CRM avec conversion devis livrés, premier entrepôt intégré à la transaction d’entreprise. Soldes, transferts, ajustements et réservations automatiques sont implémentés. Ventes/Achats et approbations sont implémentés et validés par les suites backend/frontend et la compilation ; résultats détaillés dans `progress.md`. Le prochain lot métier porte sur les réceptions/livraisons partielles, puis la facturation, les paiements et les indicateurs.

L’exception de vérification e-mail locale reste active. La référence officielle et les données existantes sont conservées. Aucune page ni opération métier simulée n’est ajoutée pour masquer un module manquant.

Lot Dashboard/notifications du 17 novembre validé : indicateurs réels par période/devise/droits, lanceur d’applications et notifications personnelles persistantes/idempotentes. Migrations appliquées, 93 tests backend et 61 frontend réussis, compilation réussie. La V1 reste à auditer contre chaque exigence, puis à valider avec le scénario E2E Playwright réel et les contrôles de sécurité/exploitation ; aucun déploiement de production n’est déclaré réalisé.

Extension financière suivante : paiements/allocations/extournes et export PDF implémentés, migrations appliquées et contrats documentés dans `payments-pdf.md`. Validation des 86 tests backend distincts sur passage global puis reprise d’une assertion de séquences, 53 tests frontend et compilation réussis ; rendu PDF final contrôlé. Résultats détaillés dans `progress.md`. La prochaine phase fonctionnelle sera le tableau de bord réel et les notifications, avant E2E, durcissement et exploitation.

État du lot financier au 17 novembre : factures directes ou multiples depuis commande, avoirs partiels, contrôle des quantités nettes et arrondis cumulés implémentés et migrés. Suites globales validées : 75 tests backend et 47 frontend, compilation réussie ; détail dans `progress.md`. Paiements et allocations, PDF puis dashboard/notifications et E2E restent nécessaires avant V1 complète. Aucune clôture de commande ou comptabilité générale n’est simulée.

Lot suivant du 17 novembre : réceptions et livraisons partielles implémentées et migrées, quantités exécutées/restantes et consommé des réservations reliés aux commandes et soldes. Contrats et résultats dans `fulfillment.md`/`progress.md`. Prochaine phase : facturation directe et issue de commandes, avoirs, paiements/allocations et PDF, avant les indicateurs et le parcours E2E final.
