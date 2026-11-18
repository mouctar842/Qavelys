# Noyau SaaS — contrat du lot de complétion

Les nouveaux modèles restent dans l’application core, sans changement de stack. UUID, dates UTC, suppression PROTECT des données d’entreprise. Aucune API de suppression de compte/entreprise/rôle n’est exposée.

## Modèles et contraintes
- Module (code unique, disponibilité), CompanyModule unique (entreprise,module), ModuleDependency unique (module,dépendance), absence d’auto-dépendance.
- CompanyInvitation : e-mail normalisé, jeton SHA-256 unique, expiration 7 jours, acceptation et révocation datées. InvitationRole lie explicitement invitation et rôle à la même entreprise, avec clés étrangères composites.
- DocumentSequence unique (entreprise,type), compteur positif, allocation sous verrou. Références préfixées et compteur de 6 chiffres, sans remise à zéro automatique.
- AuthThrottle : clé hachée par finalité et adresse/identité, compteur et fenêtre persistants entre workers. Aucune donnée de mot de passe ou de jeton dans l’audit.

## Règles
Les mutations d’administration prennent d’abord le verrou entreprise, puis contrôlent à nouveau l’adhésion et le droit. Les rôles système ne sont pas éditables ; les rôles custom n’accordent que des permissions du catalogue. Affectations de rôles et suspension/réactivation conservent un administrateur système actif. Une invitation n’annule pas une suspension existante.

L’acceptation exige une session active dont l’e-mail est celui de l’invitation ; elle est atomique et à usage unique. Le renvoi remplace le jeton et son expiration, la révocation interdit l’acceptation ; aucun jeton n’apparaît dans les réponses API. Les e-mails utilisent le transport configuré. Les nouvelles permissions sont attribuées aux administrateurs système existants par migration contrôlée.

Le noyau reste actif. Activer un module active ses dépendances disponibles ; désactiver un module encore requis par un autre est refusé. Les modules non implémentés restent signalés indisponibles et ne proposent pas d’actions métier simulées. Aucun effacement de données à la désactivation.

La récupération de mot de passe utilise les jetons Django à durée limitée. La réponse de demande reste générique, même pour une adresse inconnue ou limitée ; changer le mot de passe invalide le lien et les anciennes sessions. Validation des mots de passe Django conservée. La vérification e-mail locale n’est pas réactivée.

## API
Sous `/api/v1/` : auth/password-reset/, auth/password-reset-confirm/, auth/resend-verification/ ; auth/me/ POST pour le nom ; companies/:id/settings/, permissions/, roles/, roles/:role_id/update/, members/:member_id/roles/, members/:member_id/activate/, invitations/, invitations/:invite_id/resend|revoke/, modules/, modules/:code/enable|disable/, audit/, sequences/. Acceptation : invitations/accept/ avec jeton en POST. Mutations JSON, CSRF et permissions précises ; objets/relations filtrés par entreprise, pas de PATCH générique de statuts.
