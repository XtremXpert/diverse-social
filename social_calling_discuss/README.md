# Appels Discuss

Bouton « Appeler » du portail qui lance un appel vidéo par le Discuss natif d'Odoo (WebRTC) entre deux membres. Le module a été conçu comme variante A/B de l'appel Jitsi de `social_calling`.

## Fonctionnement

- Sur la page publique d'un profil (`/profile/<id>`), le bouton « Appeler » s'insère juste avant le bouton « Bloquer ». Il n'apparaît pas sur son propre profil.
- Le bouton est actif seulement si la personne est en ligne (`im_status` à `online`). Sinon, il est grisé.
- La route `/discuss-call/<user_id>` crée ou retrouve la conversation privée Discuss entre les deux membres, puis redirige vers `/discuss/channel/<id>`, où l'appel se lance.
- L'appelé reçoit une notification d'appel entrant par le bus (`social_calling/incoming_call`), avec le fournisseur `discuss`. Le service d'appel entrant de `social_calling` affiche la sonnerie; « Répondre » ouvre le canal.

## Configuration

Le module crée deux serveurs ICE (`mail.ice.server`) : un STUN et un TURN pointant vers le serveur coturn du projet. Ces enregistrements sont `noupdate`. Après l'installation, les modifier au besoin dans les réglages Discuss d'Odoo. Attention : l'identifiant et le mot de passe TURN sont aujourd'hui versionnés en clair dans `data/ice_servers.xml`. Ils doivent être sortis du dépôt, configurés dans les réglages Discuss, et le mot de passe changé sur le serveur coturn.

## Accès et limites

- Route réservée aux utilisateurs connectés.
- Un blocage dans un sens ou dans l'autre (`social_safety.block`) refuse l'appel.
- Un appel vers soi-même, ou vers un utilisateur inexistant ou sans contact, renvoie à `/my/messages`.
- La conversation est créée en `sudo`, car les membres sont des utilisateurs portail. L'utilisateur courant reste membre du canal.
- « Refuser » ferme seulement la sonnerie : aucune session serveur n'est enregistrée.

## Dépendances et tests

Dépend de `social_calling` (service d'appel entrant, bus), `mail` et `club_social_profile`. Le module n'a pas de tests.
