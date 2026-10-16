# Sonnerie d'appel du portail

Ce module garde la présence des membres et la fenêtre d'appel entrant du portail. Les appels eux-mêmes passent par Discuss (`social_calling_discuss`). La variante Jitsi a été retirée.

## Fonctionnement

- Sur le portail, un service JavaScript ouvre le bus et tient la présence à jour (heartbeat). Les boutons d'appel s'activent selon `im_status`.
- Le service écoute `social_calling/incoming_call` et affiche une fenêtre d'appel entrant avec sonnerie, et les boutons Répondre et Refuser. « Répondre » ouvre l'adresse reçue (`room_url`), « Refuser » ferme la fenêtre. Une session déjà traitée ne resonne pas au rejeu du bus.
- Ajoute le type de notification « Appel manqué » (`missed_call`) au réseau social.

## Mise à jour depuis la variante Jitsi (20.0.2.0.0)

La mise à jour supprime les appels Jitsi enregistrés (`social_calling.session`), leur chat (`social_calling.message`), leurs fichiers et leur historique, ainsi que les tâches planifiées, la séquence `CALL-` et les paramètres `social_calling.retention_days` et `social_calling.jitsi_server`.

## Dépendances et tests

Dépend de `club_social_profile`, `social_safety`, `social_notifications` et `portal`. Le module n'a plus de code serveur à tester.
