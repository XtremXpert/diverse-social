# Social Mobile Call

Appels audio de l'application mobile, par-dessus les appels Discuss et le SFU d'Odoo.

## Règles

- **Mêmes appels que Discuss :** l'application rejoint l'appel de la conversation (`discuss.channel.rtc.session`).
  Le site voit les participants mobiles, et peut rejoindre le même appel.
- **Toujours par le SFU :** l'application reçoit l'adresse du SFU et un jeton signé par Odoo, puis échange l'audio
  avec le SFU. Sans SFU configuré (*Paramètres → Discuss → Custom SFU Server*) ou s'il ne répond pas, rejoindre
  répond `503` et rien ne sonne.
- **Un appel passé par le SFU y reste :** Odoo repasse normalement en pair-à-pair sous trois participants. Ce module
  l'en empêche quand un canal SFU existe déjà, sinon un membre arrivé par le site n'entendrait pas l'application. Odoo
  libère le canal SFU quand le dernier participant raccroche.
- **Sonnerie :** lancer un appel fait sonner les autres membres, comme Discuss (`call.ringing` dans la conversation).
  Rejoindre ou refuser arrête la sonnerie ; refuser ne coupe pas l'appel des autres.
- **Blocage :** pas d'appel entre deux personnes dont l'une a bloqué l'autre (`403`). Hors de la conversation : `404`.
- **Maintien :** Odoo efface une session restée 75 s sans nouvelles. L'application la maintient (`ping`) toutes les
  20 à 30 s. Une session disparue (raccrochée, expirée, ou remplacée parce que le membre a rejoint un appel ailleurs)
  répond `410 call_ended` : l'application termine l'appel.
- **Noms :** toujours le pseudonyme.

## API (`/api/social/v1`, clé de portée `social_mobile`)

| Méthode | Chemin | Corps | Réponse |
|---|---|---|---|
| `GET` | `/chats/<id>/call` | | `{"call"}` |
| `POST` | `/chats/<id>/call/join` | | `{"session_id", "server": {"url", "channel_uuid", "token"}, "ice_servers", "call"}` ; `403`, `503 call_unavailable` |
| `POST` | `/chats/<id>/call/ping` | `{"session_id"}` | `{"call"}` ; `410 call_ended` |
| `POST` | `/chats/<id>/call/mute` | `{"session_id", "muted"}` | `{"call"}` ; `410 call_ended` |
| `POST` | `/chats/<id>/call/leave` | `{"session_id"}` | `{"call"}` |
| `POST` | `/chats/<id>/call/decline` | | `{"call"}` |

Appel : `{"active", "participant_count", "ringing", "participants": [{"session_id", "name", "is_self", "is_muted"}]}`.
La conversation (`/chats`, `/chats/<id>`) porte aussi `"call": {"active", "participant_count", "ringing"}`.

Avec `server`, l'application ouvre un WebSocket vers le SFU (`url` en `wss://`), envoie
`{"channelUUID": channel_uuid, "jwt": token}`, puis suit le protocole du client du SFU d'Odoo
([odoo/sfu](https://github.com/odoo/sfu), `src/client.ts`).

## Tests

Le SFU est simulé (`/v1/channel`). Les tests couvrent le jeton, la sonnerie, l'arrivée d'un participant par le site
(qui reste sur le SFU), le maintien, le micro coupé, la fin d'appel (`410`), le refus, le blocage et le SFU absent ou
injoignable.
