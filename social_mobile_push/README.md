# Social Mobile Push

Notifications natives de l'application mobile, envoyées directement à Apple (APNs) pour les iPhone et à
Google (Firebase Cloud Messaging, FCM) pour les téléphones Android.

## Ce qui est notifié

| Événement | Destinataires | Texte |
|---|---|---|
| Nouveau message (conversation à deux ou de relation) | Les autres membres de la conversation | « Nouveau message » |
| Invitation dans une relation | La personne invitée | « Vous êtes invité·e dans une relation » |
| Proposition d'un nouveau membre | Les membres qui doivent l'approuver | « Une proposition attend votre accord » |

Le texte est **discret** : ni nom, ni contenu, car l'écran verrouillé est souvent vu par d'autres. Le réglage
« Nommer l'expéditeur » donne « Message de <pseudonyme> » ; il est désactivé par défaut. La pastille de l'icône
donne le nombre de messages non lus.

Pas de notification si le destinataire a coupé le son de la conversation, n'a plus accès au réseau (chaîne de
confiance) ou n'en est plus membre. Plusieurs messages d'une même conversation non encore envoyés n'en donnent
qu'une.

## Envoi

Les notifications sont mises en file (`social_mobile.push_queue`) dans la transaction de l'événement ; la tâche
planifiée « envoyer les notifications iPhone » est déclenchée aussitôt (`_trigger`) et repasse toutes les
5 minutes. L'appel à Apple ne ralentit donc jamais la requête du membre. Réponses d'Apple :

- `410` / `Unregistered` : l'app a été désinstallée, l'appareil est retiré ;
- `BadDeviceToken` : nouvel essai sur l'autre serveur (développement ↔ production), puis correction de l'appareil ;
- `429` / `5xx` / réseau : nouvel essai (5 au plus, délai croissant) ;
- `403` : configuration refusée (équipe, clé ou bundle) ; erreur au journal, la file attend la correction.

## Android (FCM)

L'application Android enregistre un seul jeton FCM (`platform: "fcm"`, `kind: "alert"`), qui sert aux
notifications et à la sonnerie des appels (`social_mobile_call`). Odoo envoie des **messages de données
seulement**, à haute priorité : l'application construit elle-même la notification. Google ne voit donc passer
que le texte discret (« Nouveau message »), jamais le contenu d'un message.

Données d'une notification : `type: "alert"`, `kind` (`message`, `relation_invite`, `relation_proposal`),
`title`, `body`, `badge`, et `chat_id` ou `relation_id`. Appel : `type: "call"`, `event` (`ring` ou `end`),
`call_id`, `chat_id`, `caller` ; Google l'abandonne au-delà de 30 secondes. Toutes les valeurs sont du texte.

Réponses de Google :

- `UNREGISTERED`, `SENDER_ID_MISMATCH`, jeton invalide (`404`, `400 INVALID_ARGUMENT`) : l'appareil est retiré ;
- `401` : nouveau jeton d'accès, puis un nouvel essai ;
- `429` / `5xx` / réseau : nouvel essai (5 au plus, délai croissant) ;
- `403` : compte de service refusé ; erreur au journal, la file attend la correction.

Le jeton d'accès OAuth 2 (une heure) est obtenu en signant une assertion JWT RS256 avec la clé du compte de
service, et réutilisé jusqu'à cinq minutes de son échéance.

## Réglages

Paramètres → Application mobile → Notifications iPhone : identifiant d'équipe Apple, identifiant de la clé, contenu
du fichier `AuthKey_XXXXXXXXXX.p8` (Apple Developer → Keys, service « Apple Push Notifications ») et identifiant
de l'application (`com.diversecite.app`). Sans clé, rien ne part vers les iPhone.

Notifications Android : contenu du fichier JSON de la clé d'un compte de service du projet Firebase (console
Firebase → Paramètres du projet → Comptes de service → Générer une nouvelle clé privée). Sans lui, rien ne part
vers les téléphones Android.

**Essai :** Application mobile → Appareils, bouton « Notification d'essai… » sur la ligne d'un iPhone
(administrateurs système), iPhone ou Android. Un assistant permet de modifier le titre et le message (178 caractères au plus) ;
l'envoi est immédiat, sans passer par la file, et le résultat d'Apple s'affiche.

**Copies de la base :** `data/neutralize.sql` efface la clé APNs et le compte Firebase, et désactive les
appareils, pour qu'un staging restauré depuis la production n'envoie jamais rien aux téléphones des vrais membres.

Dépendances Python : `httpx[http2]` (Apple n'accepte que HTTP/2) et `PyJWT` avec `cryptography` (ES256 pour
Apple, RS256 pour Google).

## API (`/api/social/v1`, clé de portée `social_mobile`)

| Méthode | Chemin | Corps |
|---|---|---|
| `POST` | `/devices` | `{"token", "environment": "production"\|"sandbox", "kind": "alert"\|"voip", "platform": "apns"\|"fcm"}` — à chaque lancement (`platform` vaut `apns` par défaut ; un jeton FCM garde sa casse) ; un jeton déjà connu est réattribué au compte courant. `voip` : jeton PushKit, qui sert seulement à faire sonner les appels (`social_mobile_call`) ; il ne reçoit jamais de notification de message et n'a pas de notification d'essai |
| `DELETE` | `/devices` | `{"token"}` — déconnexion de l'app (sans jeton : tous mes appareils) |

Contenu d'une notification : `aps.alert`, `aps.badge`, `aps.thread-id` (`chat-<id>`), et `chat_id` ou `relation_id`
pour ouvrir le bon écran. `DELETE /me` retire aussi les appareils.
