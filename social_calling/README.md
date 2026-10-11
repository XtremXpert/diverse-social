# Appels du réseau social

Ce module garde le modèle des appels audio et vidéo entre membres, leurs tâches planifiées et la sonnerie d'appel entrant du portail. Les appels passent par un serveur Jitsi Meet.

## Fonctionnement

- Un appel (`social_calling.session`) est direct (deux membres) ou de groupe (jusqu'à 20 participants par défaut). Il est vidéo ou audio seulement, et passe par les états Ringing, Connected, Ended, Missed et Declined.
- Chaque appel reçoit un numéro `CALL-00001`, un nom de salle et un mot de passe de salle aléatoires. La durée est calculée entre le début et la fin.
- Un appel est refusé si l'un des deux membres a bloqué l'autre (`social_safety`), si un membre s'appelle lui-même ou si la salle dépasse sa capacité. Seul un administrateur peut créer un appel au nom d'un autre utilisateur.
- Le profil social offre `action_initiate_video_call` et `action_initiate_audio_call` : l'appel est créé et le destinataire est prévenu par le bus.
- Les messages du chat Jitsi peuvent être conservés dans `social_calling.message`, avec fichier joint et aperçu de lien.
- Sur le portail, un service JavaScript tient la présence à jour et affiche une fenêtre d'appel entrant avec sonnerie, et les boutons Accepter et Refuser.

## Tâches planifiées

- **Social Calling: Mark missed calls**, toutes les 5 minutes : un appel qui sonne depuis plus de 2 minutes devient manqué. Le destinataire d'un appel direct reçoit une notification « Appel manqué ».
- **Social Calling: Purge old calls (Loi 25)**, chaque jour : supprime les appels, leur chat et leurs fichiers plus vieux que la durée de rétention.

## Configuration

Paramètres système :

- `social_calling.jitsi_server` : domaine du serveur Jitsi. Par défaut, l'instance auto-hébergée de Diverse-Cité.
- `social_calling.retention_days` : durée de rétention en jours, 90 à l'installation ; 0 conserve tout.

## Accès et limites

- Les utilisateurs internes peuvent créer, lire et modifier les appels ; seuls les administrateurs les suppriment.
- Le module n'expose plus de routes : les pages `/my/calls` ont été retirées et les appels vivent dans Discuss. La fenêtre d'appel entrant et les actions du profil pointent pourtant encore vers `/my/calls/room/<id>` et `/my/calls/action`.

## Dépendances et tests

Dépend de `club_social_profile`, `social_safety`, `social_notifications` et `portal`. Les tests couvrent les états, les blocages, les salles de groupe et le cron des appels manqués.

```sh
odoo-dev test social_calling test_db
```
