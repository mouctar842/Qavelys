# Clôture commerciale — décision validée

**Choix explicite de l’utilisateur le 17 novembre 2026 : variante B, après livraison, facturation et paiement intégral.** Cette décision autorise l’implémentation décrite ci-dessous. Les variantes sont conservées comme historique de décision.

La spécification 6.3 prévoit le statut `completed` et sépare commande, livraison et facturation, mais ne fixait pas si l’encaissement conditionne la clôture. Sa règle 14.8 impose de valider les décisions métier non fixées. La variante B est désormais implémentée après la réponse explicite de l’utilisateur ; A reste uniquement l’historique de l’alternative.

Dans les deux variantes : action manuelle explicite et rejouable sur commande confirmée, permission dédiée, version attendue, verrou société et audit/horodatage/auteur. Achats : toutes les quantités reçues (services exécutés compris), sans comptabilité fournisseur hors V1. Aucune suppression, aucun nouveau mouvement et aucun arrondi différent. Brouillons aval à traiter explicitement avant clôture ; document vide, annulé ou en approbation refusé.

- **A — indépendamment des paiements** : vente intégralement livrée et quantité nette intégralement facturée après avoirs. Les soldes de paiement restent séparés et peuvent être dus après clôture.
- **B — après règlement** : mêmes conditions, plus toutes les factures liées soldées et aucun crédit client non résolu au moment de clôturer. C’est la proposition conservatrice recommandée pour le premier lot.

Exemple : 8 unités livrées, factures de 96 EUR, paiement de 50 EUR. A autorise « Terminée » ; B attend les 46 EUR restants.

La clôture ne supprime pas le droit légal de corriger une facture par avoir ou d’extourner une allocation : ces opérations restent permises, tracées et leurs soldes à jour. `completed` mémorise une clôture administrative à un instant ; son état de paiement reste indépendant et visible. Une action explicite de reprise vers confirmed, avec motif/permission/version et audit, permet de reprendre le travail sans modifier lignes, prix, documents ni effets déjà validés. Aucun changement automatique de statut historique à la lecture.

Tests prévus : livraison/réception et facturation partielles, services, paiement partiel, crédits/avoirs, brouillons aval, reprises, droits/modules/société, version périmée, rejeux et concurrence avec livraison/facturation/paiements. La politique retenue sera documentée avant code/migration.

Contrat exécuté : POST `orders/<id>/complete/` avec `version` des lignes et `closure_version` du cycle ; POST `resume/` avec ces deux versions et `reason` (8–1000 caractères). Permissions domaine.order.complete/resume et consultation de la commande. Clôture : consultation des réceptions/livraisons, et pour la vente des factures/paiements/avoirs, modules requis actifs. Métadonnées completion omises à un lecteur sans les droits financiers nécessaires. Date/auteur de clôture persistés ; historique dans l’audit.

`closure_version` augmente à chaque clôture/reprise, sans changer la version immuable des lignes. Rejeu immédiat du même événement retourne l’état sans doubler l’audit ; une requête retardée d’un cycle plus ancien renvoie 409. Les motifs de blocage sont recalculés sur les données réelles. Une reprise n’autorise pas à modifier une commande confirmée ni à réécrire ses effets. Un avoir/extourne ultérieur conserve la clôture historique et actualise les soldes/conditions ; une reprise explicite peut ensuite rouvrir le traitement commercial.
