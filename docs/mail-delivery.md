# Transport e-mail — contrat d’exploitation

Lot du 17 novembre 2026, conforme aux sections 4, 10 et 12 du cahier des charges. Aucun changement de règles métier ni de l’exception locale de vérification.

- Les envois restent synchrones avec le transport Django configuré. Timeout réseau par opération de 10 secondes par défaut (`EMAIL_TIMEOUT`), STARTTLS ou TLS implicite (`EMAIL_USE_SSL`), jamais les deux. Aucun nouvel envoi automatique, aucune file ni nouvelle dépendance.
- Un refus SMTP, une erreur réseau/TLS ou un résultat d’envoi nul produit une erreur contrôlée, sans adresse, corps, jeton, identifiant SMTP ni exception brute dans les réponses ou journaux applicatifs. Le journal `qavelys.mail` contient uniquement un événement fixe de panne.
- Inscription : HTTP 503 générique et transaction annulée si le transport échoue. L’utilisateur peut réessayer ; aucun compte ou jeton partiel ne subsiste. Une adresse déjà inscrite conserve la réponse neutre existante.
- Renvoi de vérification authentifié : HTTP 503 et nouveau jeton annulé en cas d’échec ; anciens liens conservés. Commande opérateur : erreur lisible sans trace SMTP.
- Invitations : HTTP 503 via DRF et transaction annulée ; une tentative de renvoi échouée conserve le lien précédent et l’historique. Aucun rôle ou membre créé lors d’un échec.
- Mot de passe oublié : réponse HTTP 202 identique pour compte absent, présent, limité ou transport en panne. Aucune modification du mot de passe ni des sessions ; nouvelle demande possible dans la limite existante. Le journal fixe signale la panne à l’opérateur. Le temps de réponse peut encore varier : pas de promesse de résistance à l’analyse temporelle.
- Une acceptation SMTP ne garantit pas la livraison en boîte. Une coupure après acceptation peut laisser un e-mail contenant un lien annulé ; le renvoi explicite est la procédure de reprise. Pas de promesse « exactement une fois » entre PostgreSQL et SMTP.

Tests : serveur SMTP de test exclusivement sur loopback, acceptation/refus puis reprise ; erreurs réseau et délais, absence de fuite, rollback PostgreSQL, anciens liens conservés et régression des parcours existants. Ce serveur n’est ni une dépendance ni un transport de production.

La validation du fournisseur réel, de son certificat, du domaine expéditeur et de la délivrabilité nécessite la cible et les identifiants de déploiement. Aucun message de test n’est envoyé à une boîte externe par ce lot.

Références : [envoi Django 5.2](https://docs.djangoproject.com/en/5.2/topics/email/), [réglages Django](https://docs.djangoproject.com/en/5.2/ref/settings/#email-timeout), [exceptions SMTP Python](https://docs.python.org/3.13/library/smtplib.html).
