# Appels Discuss

Bouton « Appeler » du portail qui lance un appel vidéo par le Discuss natif d'Odoo (WebRTC) entre deux membres. C'est le seul chemin d'appel du portail depuis le retrait de Jitsi.

## Fonctionnement

- Sur la page publique d'un profil (`/profile/<id>`), le bouton « Appeler » s'insère juste avant le bouton « Bloquer ». Il n'apparaît pas sur son propre profil.
- Le bouton est actif seulement si la personne est en ligne (`im_status` à `online`). Sinon, il est grisé.
- La route `/discuss-call/<user_id>` crée ou retrouve la conversation privée Discuss entre les deux membres, puis redirige vers `/discuss/channel/<id>`, où l'appel se lance.
- L'appelé reçoit une notification d'appel entrant par le bus (`social_calling/incoming_call`), avec le fournisseur `discuss`. Le service d'appel entrant de `social_calling` affiche la sonnerie; « Répondre » ouvre le canal.
- Sur toutes les pages du site, l'invitation native de Discuss (appel lancé depuis l'application mobile, par exemple) permet aussi de répondre. Odoo démarre l'objet d'appel avant ses services sur le site, et « Répondre » y plantait (`pttExtService` vide); `static/src/js/rtc_frontend_patch.js` rebranche ces services.
- Le micro doit être autorisé dans le navigateur avant de répondre, sinon Discuss rejoint l'appel micro coupé.

## Fin de l'appel quand il ne reste qu'une personne

Odoo laisse la dernière personne seule dans l'appel jusqu'à ce qu'elle raccroche. Le module termine l'appel à sa place quand il n'a jamais impliqué plus de deux personnes :

- L'historique d'appel (`discuss.call.history`) retient les membres impliqués : ceux qui ont rejoint l'appel et ceux qui y ont été invités.
- Au départ de quelqu'un (raccrocher, session expirée au bout de 75 s sans nouvelles, invitation refusée ou annulée), s'il ne reste qu'une session et plus aucune invitation, le serveur ferme cette session. Ça vaut pour le site, le portail et l'application mobile.
- Rien n'est vérifié pendant qu'un membre rejoint l'appel : répondre, ou reprendre l'appel sur un autre appareil, ferme un instant une invitation ou une session sans que personne soit parti.
- Le site affiche « Appel terminé : il ne restait que vous. » au lieu de l'avertissement d'Odoo (« Disconnected from the call by the server »), grâce au message `social_calling_discuss/ended_alone` envoyé juste avant.
- Au-delà de deux personnes impliquées (appel de groupe), la dernière personne reste dans l'appel.

## Configuration

Le module ne configure aucun serveur ICE. Les anciens serveurs STUN et TURN vers coturn (`66.70.177.199:3478`) sont supprimés à la mise à jour : coturn est retiré au profit du SFU d'Odoo (*Paramètres → Discuss → RTC Server URL*), qui a sa propre IP publique. Sans serveur ICE, Discuss utilise ses serveurs STUN par défaut.

## Accès et limites

- Route réservée aux utilisateurs connectés.
- Un blocage dans un sens ou dans l'autre (`social_safety.block`) refuse l'appel.
- Un appel vers soi-même, ou vers un utilisateur inexistant ou sans contact, renvoie à `/my/messages`.
- La conversation est créée en `sudo`, car les membres sont des utilisateurs portail. L'utilisateur courant reste membre du canal.
- « Refuser » ferme seulement la sonnerie : aucune session serveur n'est enregistrée.

## Dépendances et tests

Dépend de `social_calling` (service d'appel entrant, bus), `mail` et `club_social_profile`. `tests/test_call_end_alone.py` couvre la fin de l'appel à deux (raccrocher, refuser, session expirée), la réponse et le changement d'appareil qui ne coupent rien, et l'appel de groupe.
