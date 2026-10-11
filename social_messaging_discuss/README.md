# Messagerie Discuss

Messagerie privée entre membres par le Discuss natif d'Odoo, avec le blocage, une politique de contact et des pseudonymes. Le même canal sert aux messages et aux appels de `social_calling_discuss`.

## Fonctionnement

- `/my/messages` (alias `/my/chats`) liste les conversations privées du membre : correspondant, aperçu du dernier message, date et nombre de non-lus. Une carte « Messages » est ajoutée au portail `/my` et une entrée « Messages » au menu de site **My Network**.
- Sur la fiche d'un membre, le bouton « Message » natif est remplacé par un lien vers `/discuss-message/<user_id>`. Cette route crée ou retrouve la conversation, puis redirige vers `/discuss/channel/<id>`.
- La page Discuss publique reçoit une barre de navigation vers les messages, le réseau et la découverte.
- Pour un utilisateur non interne, Discuss affiche le pseudonyme du profil à la place du vrai nom des autres membres. Les utilisateurs internes voient les vrais noms.

## Politique de contact

Un membre ne peut ouvrir une nouvelle conversation qu'avec une connexion acceptée, un membre d'un groupe commun, ou une personne d'un cercle partagé dans un sens ou l'autre. `social_right_now` ajoute l'exception « Disponible maintenant » par le point d'extension `_smd_message_exception`. Une conversation déjà ouverte n'est jamais fermée. Sinon, le membre est renvoyé au profil avec une invitation à demander une connexion.

## Configuration

Dans **Paramètres → Discuss**, l'option « Utilisateurs internes : écrire à tout membre » (`social_messaging_discuss.internal_bypass`) permet aux employés d'écrire à tout membre. Le blocage reste appliqué.

## Accès et limites

- Le blocage `social_safety` empêche d'ouvrir une conversation et d'envoyer un message, même par la route native de Discuss. Les messages système ne sont pas bloqués.
- Ces règles ne touchent que les conversations privées (`chat`), jamais les canaux, groupes ou le clavardage en direct.
- D'après le manifeste, les notifications de `social_notifications` et l'export ou l'anonymisation de `social_privacy` ne couvrent pas encore les messages Discuss.

## Dépendances et tests

Dépend de `mail`, `social_safety`, `club_social_profile`, `portal` et `website`. Le parcours E2E `tests/e2e/test_29_messaging_policy.py` (`make test-e2e`) couvre aussi la politique de contact. Pour lancer les tests du module :

```sh
odoo-dev test social_messaging_discuss test_db
```
