# Décisions financières à valider avant implémentation

## Choix validé par l’utilisateur le 16 novembre 2026
**Arrondi au total de la facture**, choisi explicitement dans la réponse utilisateur. Cette décision remplace la proposition d’arrondi par ligne ci-dessous. Calculs intermédiaires Decimal sans arrondi de ligne ; HT du document = arrondi de la somme des HT exacts, taxe du document = arrondi de la somme des taxes exactes ; TTC = HT arrondi + taxe arrondie. Même méthode pour les commandes et les avoirs. Les montants affichés par ligne ne servent jamais à recalculer les totaux. Les prix et taux restent figés sur les documents confirmés/validés. Les paiements et allocations sont saisis à la précision de la devise.

La section 14.8 du cahier des charges exige de documenter et valider les décisions d’arrondi et de correction non fixées. Cette proposition ne modifie pas encore le moteur métier.

Proposition :
- Calculs exclusivement Decimal. Quantités et prix unitaires jusqu’à 6 décimales ; remises et taux de taxe jusqu’à 4 décimales.
- Arrondi commercial `ROUND_HALF_UP` au nombre de décimales de la devise : GNF et XOF à 0, EUR à 2 (catalogue des devises à précision documentée, pas d’hypothèse sur une devise inconnue).
- Montant HT arrondi par ligne après remise, taxe arrondie par ligne, total du document égal à la somme de ses lignes. Exemple EUR : 3 × 0,335 = 1,005 → 1,01 HT ; taxe 20 % → 0,20 ; TTC = 1,21.
- Documents validés immuables pour les quantités, montants, partenaire et devise. Un brouillon peut être corrigé ; une facture validée se corrige par avoir validé, sans effacer son historique.
- Documents annulables avant effets validés. Avec livraison, réception ou paiement déjà validé, utiliser un document de correction traçable ; pas d’effacement ou de remise directe des soldes.
- Les avoirs diminuent le dû ; pas de remboursement supérieur au crédit disponible. Les remboursements bancaires externes ne sont pas exécutés automatiquement par Qavelys.

Variante possible : calculer et arrondir la taxe au total de la facture plutôt que par ligne. Cela change certains centimes et doit être choisi avant les tests d’acceptation financiers.
