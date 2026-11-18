# Référentiel partagé — contrat

Application Django `reference`, API sous `/api/v1/companies/:id/reference/`. Les contacts sont contrôlés par le module `contacts` et les produits/catégories/taxes/unités par `catalog`. Chaque opération vérifie adhésion active, permission précise et module activé. Listes paginées, recherche, filtres, détails et actions d’archivage, jamais de suppression physique.

- Partner : UUID, société, coordonnées, indicateurs client/fournisseur, statut actif/archivé. Au moins un des deux indicateurs client/fournisseur. Un partenaire peut être les deux.
- ProductCategory : UUID/société, nom unique par société, parent éventuel de même société ; cycles refusés sous verrou société.
- UnitOfMeasure : catalogue global, UUID, nom/symbole/catégorie. Une unité de référence par produit ; aucune conversion implicite de quantités en V1.
- Tax : UUID/société, nom unique par société, taux Decimal(9,4), de 0 à 100 %, indicateur actif. Les documents futurs conserveront leurs taux figés.
- Product : UUID/société, SKU normalisé en majuscules et unique dans cette société, type stockable/consommable/service, catégorie éventuelle de même société, unité globale, prix vente/coût Decimal(20,6) positifs ou nuls, actif.
- ProductTax : lien de même société produit/taxe, unicité, contraintes composites. Historique de prix alimenté lors d’une modification effective et audit sans secrets.

Clés étrangères PROTECT pour les références métier, index de listes société/statut et société/actif, unicités `(id,company)` pour les références composites. Archives conservées et consultables par filtre explicite ; les documents nouveaux devront refuser les références archivées.

Routes : partners/, products/, categories/, taxes/, units/. Détail par UUID pour les quatre ressources d’entreprise ; POST création, POST `:id/update/` édition et POST `:id/archive/` pour les contacts/produits/taxes. Le catalogue global d’unités est en lecture seule. Montants transmis sous forme de chaînes décimales, jamais de float.

Le catalogue de modules passe contacts/catalog à disponible uniquement à la livraison du lot et les administrateurs système reçoivent les permissions correspondantes. Les entreprises les activent via la page Modules ; aucune donnée réelle n’est injectée pour illustrer les écrans.
