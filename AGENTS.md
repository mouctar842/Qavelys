# Instructions permanentes — Qavelys

- Nouvelle priorité utilisateur du 17 novembre 2026 : préparation à la production en suspens ; exécuter progressivement les sept chantiers de `docs/seven-workstreams-request.md` avec audit/contrats dans `docs/seven-workstreams-plan.md`. Cette demande autorise l’extension employés et Production, sans réécrire le cahier maître ni inventer les décisions de valorisation/qualité manquantes.

- Répondre en français. Lire intégralement `QAVELYS_MASTER_SPEC.md` au début de chaque session et le consulter de nouveau avant chaque module. C'est la source officielle ; `docs/master-spec.md` est uniquement un lien de lecture.
- Respecter la stack et les phases de la spécification. Travailler par petits lots : annoncer, documenter les contrats et contraintes, implémenter, migrer, tester, corriger, mettre à jour `docs/progress.md`, rendre compte.
- Aucune modification majeure de sécurité, architecture, périmètre ou règles métier sans validation de l'utilisateur.
- Ne supprimer aucun fichier ni aucune donnée existante sans accord. Ne jamais écraser le cahier des charges.
- Aucune donnée fictive en production, aucun bouton inerte ni faux indicateur. Aucune fonctionnalité terminée sans tests exécutés concluants.
- Chaque accès métier vérifie côté serveur : adhésion active, entreprise active, permission, module et cohérence des relations. Les caches frontend incluent l'entreprise.
- Conserver les transactions/verrous PostgreSQL, UUID, Decimal, UTC, sessions Django et CSRF. Ne jamais remplacer PostgreSQL par SQLite pour prétendre valider la concurrence.
- Ne jamais versionner secrets, environnement virtuel ou dépendances installées.
- Logo d’entreprise fourni par l’entreprise, import privé et versions conservées ; voir docs/platform-branding.md. Console plateforme séparée, aucun bypass des contrôles d’adhésion métier par is_staff/is_superuser.
- Employés, départements et missions : lire `docs/people.md`. Module hr explicite ; Employee distinct de User/Membership, lien facultatif vers une adhésion de la même société. Archivage RH sans suspension automatique du compte, sans rôle ajouté ; invitations et accès restent dans leurs services existants. Conserver FK composites, clés rejouables et versions d’édition.
- Clients/Fournisseurs : lire `docs/partner-workspaces.md`. Partner commun, pas de fusion automatique ni duplication pour ajouter le second profil. Conserver les champs de la relation opposée et les anciens liens /contacts. Activités et soldes vérifiés selon droits/modules sources ; aucune facture ou dette fournisseur fictive.
- Décision de clôture validée le 17 novembre 2026 : vente terminée après livraison, facturation nette et paiement intégral ; achats après réception complète. Reprise explicite motivée, sans modifier les effets validés ; lire docs/order-completion-proposal.md.
- Documenter les limites et tests non exécutés explicitement. Maintenir les documents API, base, sécurité et progression.
- Exception expressément demandée par l’utilisateur le 16 novembre 2026 : vérification e-mail temporairement désactivée en local avec `REQUIRE_EMAIL_VERIFICATION=0` et `DJANGO_DEBUG=1`. Ne pas la réactiver dans cet environnement sans demande. Conserver l’implémentation pour la suite ; elle reste obligatoire hors DEBUG. Les comptes ne sont pas marqués artificiellement comme vérifiés.
- Décision financière validée par l’utilisateur : arrondi au total de la facture, sans arrondi intermédiaire de ligne, à la précision ISO de la devise. Lire `docs/financial-policy-proposal.md` et utiliser `core.money` avec Decimal. Ne pas revenir à un arrondi par ligne.
