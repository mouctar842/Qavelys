# Collaborateurs — annuaire, organisation et missions

Extension explicitement demandée dans les sept chantiers. Cahier maître relu ; aucune paie, contrat de travail, congé, règle juridique ou comptabilité ajoutés par ce lot.

## Contrats et séparation des responsabilités

Module `hr` (« Équipe et missions »), dépendant seulement du noyau. Activation explicite par société ; désactivation bloque les API du module et conserve toutes les données. Aucun employé créé depuis les membres existants, aucun compte créé depuis une fiche employé. Un membre externe peut rester sans fiche ; une fiche peut rester sans accès. Nom/contact/poste/responsabilités sont propres à la fiche de l’entreprise et ne changent pas le profil global User.

Permissions nécessaires : `hr.employee.view/manage`, `hr.department.view/manage`, `hr.mission.view/manage`. Chaque mutation exige aussi le droit de lecture de sa ressource. Les seuls administrateurs système existants et futurs reçoivent ces nouvelles permissions ; les rôles personnalisés sont inchangés. Modèle de rôle « Responsable RH » disponible explicitement, sans attribution automatique ; il peut consulter les membres (members.view), sans gérer les rôles ou suspendre les accès. Les fiches ne confèrent aucun rôle : affectation et invitations restent dans les mécanismes existants.

`Department` : UUID, société, nom (100), description (2000), statut actif/archivé, version, clé de requête. Nom unique insensible à la casse par entreprise. Archivage ne déplace pas les salariés ; un département archivé reste affiché sur les anciennes fiches, mais n’est plus sélectionnable pour une nouvelle affectation.

`Employee` : UUID, société, matricule (40, majuscules/chiffres/tiret/underscore), nom (150), contact professionnel facultatif, téléphone, poste (150), responsabilités (4000), département facultatif, lien facultatif vers Membership, statut actif/archivé, version, clé de requête. Matricule unique par entreprise, lien Membership unique par entreprise même sur fiche archivée (détacher explicitement pour réutiliser). Contraintes étrangères composites société/département et société/adhésion, ON DELETE RESTRICT. Aucun lien direct permissif vers un utilisateur global. Pour choisir/changer un lien non nul : members.view, adhésion et utilisateur actifs, même société ; un ancien lien suspendu peut être conservé ou détaché. Archivage RH ne suspend ni le membre ni l’utilisateur et ne change pas ses rôles ; les missions existantes restent consultables et gérables.

`EmployeeMission` : UUID, société, employé, titre (200), description (4000), échéance facultative (date), statut à faire/en cours/terminée/annulée, date de fin UTC, version, clé de requête. Affectation à un employé actif de la même société. Transitions explicites : démarrer (à faire → en cours), terminer (à faire/en cours → terminée), annuler (à faire/en cours → annulée), rouvrir (terminée/annulée → à faire, date de fin effacée). Pas de changement de statut par édition générique. Éditer titre/description/échéance/affectation seulement avant fin/annulation ; historique complet par audit. Aucun moteur de tâches parallèle à un module existant : il n’y a actuellement que les activités CRM, qui restent inchangées et liées aux prospects.

## API, intégrité et concurrence

Sous `companies/{company}/hr/` : GET/POST `employees/`, `departments/`, `missions/` ; GET/POST `{resource}/{id}/` ; POST employés/départements `{id}/archive|restore/` et missions `{id}/start|complete|cancel|reopen/` ; GET `lookups/` selon droits réels. Pas de DELETE, PATCH ou statut éditable. Listes : recherche, état, département/employé selon ressource, tri contrôlé et pagination de 25. Entrées étrangères rejetées, réponses privées/no-store.

Création : clé UUID `request_key` ; empreinte du contenu validé, rejouable sans deuxième objet/audit, même clé/autre contenu → 409. Éditions/actions : `version` attendue obligatoire, incrément après changement ; version périmée → 409. Toutes les mutations prennent le verrou de société avant les contrôles/relations, comme l’administration existante. Unicités SQL et FK composites complètent les contrôles serveur. Aucun rôle RH n’ouvre les données d’une autre société, même pour un Super Admin sans adhésion.

Frontend : annuaire employé et fiches, formulaires validés, départements et missions, filtres/recherche/tri/pagination, confirmations d’archivage et transitions, liens vers les accès utilisateurs selon permission, état clair « Sans accès Qavelys ». Caches par entreprise ; reset au changement de société. Champs professionnels seulement, aucun salaire ou document personnel.

## Vérifications

Lot validé le 18 novembre 2026 : 157 tests backend complets puis 2 ciblés, 87 frontend, build strict et 5 E2E réussis, dont le nouveau parcours RH. Captures ordinateur/mobile sombre inspectées. Migrations 0001/0002 appliquées ; erreurs initiales de fixture et délais sous charge résolues, libellés de sélections fiabilisés. Aucun rôle/module attribué ou activé automatiquement ; détails et journaux dans `progress.md`.

PostgreSQL réel : migrations, FK composites et unicités, rejouabilité et course de création, versions concurrentes, autorisations/modules/société active, aucun changement d’accès lors des actions RH, missions et archivage, CSRF, UUID étrangers. Frontend : création/édition/recherche, erreurs, formulaires et permissions, transitions. E2E séparé : activation → département → employé sans compte → mission → fin → archivage, preuve persistante/API, changement d’entreprise, aucun compte ajouté. Résultats dans progress.md.

## Utilisation

1. Dans l’entreprise concernée, ouvrir Modules et activer « Équipe et missions ». Le module n’est jamais activé automatiquement par une migration.
2. Créer les départements, puis enregistrer les employés avec leurs matricules, postes et responsabilités. Laisser « Sans accès Qavelys » pour une personne sans compte.
3. Pour une personne disposant déjà d’une adhésion, sélectionner cet accès dans sa fiche, avec members.view. Pour inviter une nouvelle personne, utiliser Invitations, puis lier sa fiche après acceptation ; aucun mot de passe n’est défini dans l’annuaire.
4. Attribuer les missions depuis la fiche employé ; utiliser Démarrer, Terminer, Annuler la mission ou Rouvrir selon l’état. Une mission terminée conserve sa date de fin ; la réouverture est auditée.
5. Archiver une fiche pour la retirer de l’annuaire actif. Ses missions, son historique et son éventuel accès sont conservés. Pour retirer réellement un accès à l’entreprise, utiliser sa suspension dans Collaborateurs ; le dernier administrateur actif reste protégé.
6. Pour déléguer l’administration RH, ajouter le modèle Responsable RH depuis Rôles et accès, examiner ses droits puis l’attribuer explicitement via le mécanisme habituel. Il ne donne pas le droit de gérer les rôles ou de suspendre des membres.
