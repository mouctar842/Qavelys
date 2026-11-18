# Règles métier

Le cahier des charges officiel fait autorité. Les seules opérations actuelles sont celles du noyau : compte vérifié avant connexion, accès via adhésion active d’une entreprise active et permission précise, création d’espace atomique, impossibilité de suspendre le dernier administrateur actif via l’API. Une suspension répétée ne duplique pas l’audit.

Les modules désactivés devront conserver l’historique ; aucune opération métier n’existe encore. Les règles de stocks, taxes, quantités, facturation partielle, avoirs, allocations et approbations sont intégralement à implémenter dans l’ordre du cahier des charges. Les types pays/devise sont actuellement validés syntaxiquement (2 et 3 lettres majuscules), sans catalogue ISO complet.
