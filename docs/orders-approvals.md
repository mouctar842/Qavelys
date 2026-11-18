# Commandes et approbations — contrat du lot

Extension clôture du 17 novembre 2026 : `complete` et `resume` implémentés selon `order-completion-proposal.md`, choix utilisateur après règlement intégral. Achats : réception complète. Date/auteur, compteur de cycle distinct, motif de reprise, droits de consultation et verrou société. Les descriptions suivantes annonçant la clôture comme future sont l’historique du premier lot.

Extension du 17 novembre 2026 : réceptions/livraisons partielles reliées aux commandes dans `fulfillment.md`. Une première validation aval bloque l’annulation de commande ; les mentions ci-dessous décrivant ces opérations comme futures datent du premier lot. Le statut d’exécution et les quantités exécutées/restantes sont désormais séparés du statut de commande. La clôture commerciale `completed` reste à intégrer avec la facturation.

Applications Django `sales`, `purchases`, `approvals`, avec primitives communes dans `core`. API `/companies/{id}/sales/orders/`, `/purchases/orders/`, `/approvals/rules/` et `/approvals/requests/`. Même société obligatoire pour client/fournisseur, produit, entrepôt, prospect, rôle et approbateur ; FK composites SQL, UUID et PROTECT. Aucune suppression de document ni ligne historique.

## Documents

Devis = commande client brouillon ou en approbation ; confirmation transforme le même document en commande avec sa référence unique. Commande fournisseur selon le même cycle. Statuts `draft`, `pending_approval`, `confirmed`, `completed`, `cancelled` ; pas de modification de statut par formulaire générique. Ce lot ne permet pas encore de terminer une commande : livraison, réception et facturation seront reliées dans les lots suivants.

POST création : `request_key` UUID obligatoire et contenu normalisé haché, rejeu identique sans doublon. Champs : `partner_id` client/fournisseur, `warehouse_id`, `order_date`, `notes`, `lead_id` facultatif en vente, `lines` (1 à 200, produit, description, quantité positive, prix positif ou nul, remise et taxe entre 0 et 100). Prix et taxe facultatifs à la première saisie : défauts réels du catalogue, figés sur la ligne. Quantités/prix Decimal à 6 décimales, taux à 4 ; refus des floats JSON. Totaux `core.money` avec arrondi au total, conformément au choix utilisateur. Chaque ligne conserve produit/type/unité/description, prix et taux ; totaux de ligne exacts stockés sans arrondi intermédiaire.

POST `{id}/update/` : version attendue obligatoire, seulement brouillon. Crée une nouvelle version et de nouvelles lignes, conserve les anciennes. POST `submit/`, `confirm/`, `reopen/`, `cancel/` : version attendue obligatoire, actions idempotentes pour une même version. Réouverture uniquement avant confirmation, invalide les demandes d’approbation en cours et rend le document éditable. Une modification de document approuvé impose une nouvelle approbation ; aucun document confirmé n’est éditable. Annulation avant opérations aval : libération des réservations ; lorsque réceptions/livraisons/factures seront ajoutées, ces effets devront bloquer l’annulation et imposer des corrections traçables.

Confirmation : document non vide, partenaire/entrepôt actifs et produits actifs ; type et unité cohérents avec les snapshots. Approbation courante obligatoire si une règle active correspond au total TTC. Vente : réservation transactionnelle dans les emplacements internes actifs de l’entrepôt choisi, disponible = physique - réservé. Réserve ce qui existe, garde le manque en attente ; aucun mouvement physique ni réservation pour un service. POST `reserve/` réessaie le manque sans doubler les réservations. Libération conserve les lignes de réservation historiques.

Après confirmation d’une vente ou d’un achat, l’unité et la nature stock/service du produit sont protégées même sans stock disponible. Cela permet aux commandes en attente de réapprovisionnement de rester exécutables. Un nouveau produit est requis pour changer cette interprétation des quantités.

## Approbations

Règles par type `sales_order`/`purchase_order`, intervalle TTC **minimum inclus, maximum exclu**, maximum vide = sans plafond. Les intervalles actifs ne doivent pas se chevaucher (verrou entreprise), rôle de la même société ayant au moins un membre actif ; absence de règle = confirmation directe. Aucun seuil arbitraire n’est préconfiguré.

Permissions `approvals.rules.view/manage`, `approvals.requests.view/decide` ; chaque décision exige en plus le rôle approbateur de la demande, l’adhésion active et le module du document. L’auteur peut décider uniquement s’il satisfait ces conditions ; aucune séparation auteur/approbateur supplémentaire n’est imposée dans le cahier des charges.

Une demande conserve règle/version, intervalle et rôle, version du document, auteur et date. Décision unique `approved`/`rejected`, commentaire conservé. Rejet remet le document en brouillon ; nouvelle soumission crée une nouvelle tentative, sans écraser l’historique. Rejeu d’une même décision retourne la décision existante ; une décision contraire est refusée. Changement de règle rend ses demandes en attente obsolètes et remet les documents concernés en brouillon ; confirmations revérifient toujours la règle active et sa version. Les décisions précédentes restent consultables.

## Parcours et accès

Listes recherchables, filtrables, triables, paginées ; fiches avec lignes, totaux, version, approbations, réservations et audit. Actions filtrées par permissions dans l’interface, contrôle indépendant côté serveur. Pas de bouton réception/livraison/facture tant que son opération n’est pas implémentée.

CRM → devis : formulaire prérempli à partir du prospect réel, création persistée et auditée avec `crm.manage`, module CRM et droits ventes. Prospect déjà lié à un contact : même client exigé ; sinon rattachement atomique au client choisi. Plusieurs devis possibles volontairement, une même clé de création ne produit qu’un document.
