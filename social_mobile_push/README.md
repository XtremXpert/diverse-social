# Social Mobile Push

Notifications iPhone natives (APNs) de l'application mobile, envoyées directement à Apple.

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

## Réglages

Paramètres → Application mobile → Notifications iPhone : identifiant d'équipe Apple, identifiant de la clé, contenu
du fichier `AuthKey_XXXXXXXXXX.p8` (Apple Developer → Keys, service « Apple Push Notifications ») et identifiant
de l'application (`com.diversecite.app`). Sans clé, rien ne part.

**Essai :** Application mobile → Appareils, bouton « Notification d'essai… » sur la ligne d'un iPhone
(administrateurs système). Un assistant permet de modifier le titre et le message (178 caractères au plus) ;
l'envoi est immédiat, sans passer par la file, et le résultat d'Apple s'affiche.

**Copies de la base :** `data/neutralize.sql` efface la clé et désactive les appareils, pour qu'un staging restauré
depuis la production n'envoie jamais rien aux iPhone des vrais membres.

Dépendance Python : `httpx[http2]` (Apple n'accepte que HTTP/2).

## API (`/api/social/v1`, clé de portée `social_mobile`)

| Méthode | Chemin | Corps |
|---|---|---|
| `POST` | `/devices` | `{"token", "environment": "production"\|"sandbox"}` — à chaque lancement ; un jeton déjà connu est réattribué au compte courant |
| `DELETE` | `/devices` | `{"token"}` — déconnexion de l'app (sans jeton : tous mes appareils) |

Contenu d'une notification : `aps.alert`, `aps.badge`, `aps.thread-id` (`chat-<id>`), et `chat_id` ou `relation_id`
pour ouvrir le bon écran. `DELETE /me` retire aussi les appareils.
