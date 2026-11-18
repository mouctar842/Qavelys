# PROMPT MAÎTRE — QAVELYS ERP

Tu es un ingénieur logiciel senior, architecte full-stack et expert en conception d'ERP SaaS multi-entreprises.

Tu travailles sur **Qavelys**, un ERP généraliste déjà en cours de développement.

Ta mission est de corriger, améliorer et compléter l'application existante en intervenant sur l'ensemble du système : frontend, backend, base de données, API, logique métier, authentification, autorisations, sécurité, architecture multi-entreprises et intégration entre modules.

## RÈGLE FONDAMENTALE

**Tu dois t'adapter entièrement à l'environnement existant de Qavelys.**

Avant toute modification :

1. Analyse intégralement la structure du projet.
2. Identifie les technologies, frameworks, bibliothèques et conventions utilisés.
3. Étudie l'architecture frontend et backend.
4. Examine le schéma de base de données, les relations, les migrations et les contraintes.
5. Analyse le fonctionnement de l'authentification et des permissions.
6. Identifie les modules existants et leurs dépendances.
7. Comprends la logique multi-entreprises et le sélecteur d'entreprise.
8. Identifie les fonctionnalités déjà développées pour éviter de les recréer inutilement.

Ne change pas de stack technologique sans nécessité démontrée.

Ne reconstruis pas Qavelys depuis zéro.

Ne supprime aucune fonctionnalité opérationnelle.

Ne crée pas de systèmes parallèles lorsqu'une fonctionnalité équivalente existe déjà.

Chaque intervention doit être cohérente avec l'architecture, le design, les conventions et la logique métier de Qavelys.

Les corrections doivent être réelles et fonctionnelles, pas simplement visuelles.

---

# CHANTIER 1 — GESTION DES COLLABORATEURS

Améliore complètement le système de gestion des collaborateurs.

L'administrateur d'une entreprise doit pouvoir créer, modifier, organiser, rechercher, désactiver et gérer les collaborateurs de son entreprise.

Chaque collaborateur doit pouvoir être associé à un poste, un département, des responsabilités et des rôles.

Il doit être possible d'attribuer des missions et de définir les accès aux fonctionnalités de l'ERP.

Distingue correctement les employés enregistrés dans les ressources humaines des utilisateurs disposant d'un accès à Qavelys.

Un employé ne doit pas obligatoirement disposer d'un compte utilisateur.

Un utilisateur externe autorisé peut accéder à une entreprise sans être son salarié.

Respecte l'architecture multi-entreprises : un utilisateur peut appartenir à plusieurs entreprises et posséder des rôles différents dans chacune.

Assure la cohérence avec les modules RH, tâches, utilisateurs et permissions existants.

# CHANTIER 2 — RÔLES ET PERMISSIONS

Revois intégralement la présentation et le fonctionnement de la gestion des rôles et permissions.

## Organisation des permissions

Les permissions doivent être regroupées clairement **par module**.

Analyse les modules et permissions déjà présents dans Qavelys pour construire automatiquement cette organisation.

N'invente pas de permissions arbitraires et ne supprime pas celles qui existent.

Remplace l'affichage des identifiants techniques par des libellés compréhensibles.

Améliore l'ergonomie des formulaires, la sélection des permissions et la gestion des rôles.

## Rôles prédéfinis

Qavelys doit disposer de rôles prédéfinis essentiels correspondant aux besoins habituels des entreprises.

Prévois notamment les rôles pertinents parmi les suivants :

- Administrateur d'entreprise
- Gestionnaire
- Comptable
- Responsable RH
- Commercial
- Responsable des achats
- Gestionnaire de stock
- Responsable de production
- Employé

Adapte ces rôles aux modules réellement disponibles.

Attribue les permissions appropriées selon les responsabilités de chaque rôle et le principe du moindre privilège.

Les rôles prédéfinis doivent être disponibles pour les entreprises concernées, sans duplication lors des initialisations.

Permets également la création de rôles personnalisés.

Les rôles système sensibles doivent être protégés contre les modifications dangereuses.

Toutes les autorisations doivent être vérifiées côté serveur, et pas uniquement dans l'interface.

# CHANTIER 3 — JOURNAL D'AUDIT

Refonds le journal d'audit afin qu'il soit compréhensible par un administrateur non technique.

Actuellement, les événements et les données techniques rendent la page difficile à exploiter.

Transforme les événements en descriptions claires permettant de comprendre :

- Qui a effectué l'action.
- Quelle action a été réalisée.
- Sur quel élément.
- À quel moment.
- Dans quelle entreprise.
- Quel changement a été effectué.

Améliore la présentation, la recherche, les filtres et la consultation des détails.

Les données techniques doivent rester disponibles pour les besoins d'investigation, mais ne doivent pas encombrer l'interface principale.

Conserve l'intégrité, la traçabilité et la sécurité du journal d'audit.

Les événements doivent être correctement isolés par entreprise, sauf dans le cadre des fonctions de supervision explicitement autorisées au Super Admin.

# CHANTIER 4 — NUMÉROTATION DES DOCUMENTS

Améliore le système actuel de séquences documentaires.

Renomme l'interface de manière compréhensible, par exemple « Numérotation des documents ».

Remplace les identifiants techniques visibles par des noms métiers.

Organise les séquences par module et présente clairement leur utilité.

Permets la configuration des formats et préfixes lorsque cela est autorisé.

Affiche un aperçu du prochain numéro généré.

Analyse le fonctionnement existant avant toute modification.

Garantis l'unicité des numéros, y compris lorsque plusieurs utilisateurs créent simultanément des documents.

Préserve les références déjà attribuées et les relations avec les documents existants.

Respecte les contraintes de traçabilité et les obligations de numérotation applicables.

# CHANTIER 5 — CLIENTS ET FOURNISSEURS

Revois la gestion des clients et des fournisseurs.

Actuellement, leurs formulaires de création sont pratiquement identiques, alors que leurs fonctions commerciales sont différentes.

Crée deux expériences métier clairement distinctes.

## Espace Clients

L'interface doit être adaptée à la gestion commerciale, aux ventes, aux factures, aux paiements, aux créances et au suivi de la relation client.

## Espace Fournisseurs

L'interface doit être adaptée aux achats, aux approvisionnements, aux commandes, aux livraisons, aux factures fournisseurs et aux règlements.

Les formulaires doivent présenter les informations pertinentes selon le profil.

Analyse les données et modules déjà existants pour déterminer les champs nécessaires.

## Référentiel commun

Une même personne ou entreprise peut être simultanément cliente et fournisseur.

Il faut donc permettre ce double profil sans créer inutilement des doublons.

Conserve les informations communes dans un référentiel cohérent et distingue les données propres à chaque relation commerciale.

Préserve les données existantes, les historiques et les relations avec les autres modules.

Améliore également les libellés, les formulaires, les fiches détaillées, les recherches et la navigation.

# CHANTIER 6 — CRÉATION DU MODULE PRODUCTION

Conçois et intègre un véritable module Production dans Qavelys.

Ce module doit répondre aux besoins des entreprises qui fabriquent, assemblent ou transforment des produits.

Il doit notamment pouvoir couvrir :

- Gestion des matières premières.
- Nomenclatures de fabrication.
- Ordres de fabrication.
- Planification de la production.
- Gestion des ressources, ateliers et machines.
- Suivi des opérations de fabrication.
- Gestion des quantités produites.
- Suivi des pertes et rebuts.
- Calcul des coûts de production.
- Contrôle qualité.
- Traçabilité des lots.
- Gestion des produits finis.
- Indicateurs et tableaux de bord de production.

Adapte la conception aux structures et fonctionnalités déjà présentes.

Le module doit s'intégrer correctement avec les stocks, les achats, les ventes, la comptabilité et les autres modules concernés.

Les mouvements de matières premières et de produits finis doivent être cohérents avec le système de stock existant.

Évite toute duplication des mécanismes de stock, de produits, de fournisseurs ou de comptabilité.

Prévois les règles de validation, les contrôles métier et les permissions nécessaires.

Le module doit pouvoir être activé ou désactivé selon les besoins de chaque entreprise.

L'ensemble doit fonctionner dans l'architecture multi-entreprises de Qavelys.

# CHANTIER 7 — SUPER ADMINISTRATEUR GLOBAL

Développe ou complète l'espace Super Admin de Qavelys.

Le Super Admin est l'administrateur de la plateforme SaaS dans son ensemble.

Il doit disposer d'un espace distinct de l'administration des entreprises.

## Gestion des entreprises

Le Super Admin doit pouvoir :

- Consulter toutes les entreprises créées sur Qavelys.
- Rechercher et filtrer les entreprises.
- Consulter leurs informations générales.
- Consulter leur statut.
- Activer, suspendre et réactiver une entreprise.
- Gérer les administrateurs des entreprises.
- Consulter les modules activés.
- Superviser les utilisateurs de la plateforme.
- Gérer les abonnements et offres lorsque ces fonctionnalités existent.
- Consulter les événements administratifs importants.

## Tableau de bord global

Prévois un tableau de bord permettant de suivre l'activité globale de Qavelys.

Les statistiques doivent provenir des données réelles de la plateforme.

## Sécurité

Distingue rigoureusement les privilèges du Super Admin, des administrateurs d'entreprise et des collaborateurs.

Le Super Admin doit pouvoir administrer toutes les entreprises sans disposer automatiquement d'un accès libre à leurs données métier confidentielles.

Toute intervention sensible doit être autorisée, sécurisée et journalisée.

Aucune entreprise ne doit pouvoir accéder aux données d'une autre entreprise.

---

# EXIGENCES TRANSVERSALES OBLIGATOIRES

## 1. Frontend

Respecte l'identité visuelle actuelle de Qavelys.

Conserve le style moderne et dynamique, ainsi que les thèmes clair et sombre.

Améliore les interfaces concernées pour qu'elles soient professionnelles, intuitives, responsives et accessibles.

Évite les interfaces surchargées et l'affichage inutile d'informations techniques.

Prévois correctement les états de chargement, les erreurs, les confirmations et les interfaces vides.

## 2. Backend

Toutes les fonctionnalités doivent être reliées à une véritable logique métier.

Implémente ou adapte les services, contrôleurs, validations, API et mécanismes nécessaires selon l'architecture existante.

Ne crée pas de simples interfaces sans fonctionnement réel.

## 3. Base de données

Analyse le schéma existant avant de créer ou modifier des tables.

Réutilise les modèles et relations existants lorsque cela est pertinent.

Prévois les migrations nécessaires.

Protège l'intégrité référentielle et les données déjà enregistrées.

Ne supprime aucune donnée existante sans nécessité explicite et validation.

## 4. Multi-entreprises

Qavelys permet à un utilisateur de gérer plusieurs entreprises depuis un même compte, avec un sélecteur d'entreprise.

Préserve ce fonctionnement.

Toutes les nouvelles fonctionnalités doivent respecter le contexte de l'entreprise sélectionnée.

Les données, rôles, permissions, paramètres et opérations doivent être correctement isolés entre entreprises.

## 5. Sécurité

Vérifie systématiquement les permissions côté serveur.

Protège les opérations sensibles.

Empêche les élévations de privilèges.

Valide les données entrantes.

Préserve la confidentialité des informations.

Respecte les mécanismes de sécurité existants et renforce-les lorsque nécessaire.

## 6. Intégration

Chaque nouvelle fonctionnalité doit être intégrée aux modules concernés.

Évite les incohérences entre les données, les écrans et les processus métier.

Ne duplique pas les fonctionnalités déjà disponibles.

## 7. Qualité et tests

Pour chaque chantier :

- Vérifie les fonctionnalités existantes.
- Implémente les modifications nécessaires.
- Ajoute ou adapte les tests pertinents.
- Vérifie les autorisations et l'isolation multi-entreprises.
- Teste les API et les opérations métier.
- Vérifie les interactions frontend/backend.
- Contrôle les régressions.
- Corrige les erreurs détectées.

N'annonce pas qu'une fonctionnalité est terminée si elle n'a pas été correctement intégrée et vérifiée.

---

# MÉTHODE D'EXÉCUTION

Travaille progressivement et méthodiquement.

**Phase 1 — Audit technique**

Analyse le projet et identifie les composants concernés par les sept chantiers.

**Phase 2 — Planification**

Établis un plan d'implémentation cohérent avec les dépendances entre fonctionnalités.

Indique les éléments déjà disponibles, ceux à corriger et ceux à développer.

**Phase 3 — Implémentation**

Réalise les corrections et développements directement dans le projet existant.

Traite les dépendances techniques dans le bon ordre.

**Phase 4 — Intégration**

Assure la cohérence entre frontend, backend, base de données, API, permissions et modules.

**Phase 5 — Vérification**

Exécute les tests disponibles, corrige les erreurs détectées et vérifie les fonctionnalités de bout en bout.

**Phase 6 — Bilan**

Présente un rapport indiquant :

- Les chantiers réalisés.
- Les fichiers importants modifiés.
- Les migrations effectuées.
- Les tests exécutés et leurs résultats.
- Les éventuelles limitations.
- Les fonctionnalités restant à terminer.

# CONSIGNES FINALES

Ne te contente jamais de modifier uniquement l'apparence d'une page.

Ne simule pas des fonctionnalités avec des données fictives dans le produit final.

N'introduis pas de dépendances inutiles.

N'effectue pas de refonte globale non justifiée.

Ne casse pas les fonctionnalités déjà opérationnelles.

Ne remplace pas les systèmes existants sans avoir vérifié s'ils peuvent être réutilisés.

Ne modifie pas arbitrairement les règles métier.

Ne réalise aucune opération destructive sur les données de production sans autorisation explicite.

Si une décision importante dépend d'une information absente du projet, signale-la au lieu d'inventer un comportement.

**Ton objectif est de faire évoluer Qavelys vers un ERP SaaS multi-entreprises complet, professionnel, cohérent, sécurisé et réellement opérationnel.**

Commence maintenant par l'audit de l'environnement existant, puis exécute progressivement l'ensemble des sept chantiers en respectant toutes les exigences de ce document.