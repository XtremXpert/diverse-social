# Social Mobile Chat

Messagerie de l'application mobile, par-dessus Discuss et `social_messaging_discuss`.

## Règles

- **Conversations :** les chats à deux (`discuss.channel` de type `chat`) et les conversations de relation
  (canal de groupe de `social_relation`, réservé à ses membres acceptés).
- **Ouvrir une conversation** suit la politique de contact de `social_messaging_discuss` : connexion, groupe ou
  cercle commun, ou « Disponible maintenant ». Une conversation existante reste toujours ouverte.
- **Blocage :** impossible d'ouvrir une conversation ou d'envoyer un message entre deux personnes dont l'une a
  bloqué l'autre (contrôle de `message_post`).
- **Noms :** toujours le pseudonyme (`_display_name_for_user`), jamais le vrai nom.
- **Texte :** le corps est envoyé et rendu en texte brut (aucun HTML interprété), 4000 caractères au plus.
- **Messages vocaux :** comme ceux de Discuss (pièce jointe marquée vocale, `discuss.voice.metadata`), donc lus
  par le lecteur vocal du site. L'application envoie de l'AAC en `.m4a` (`audio/mp4`, 3 Mo au plus) ; le format
  est vérifié sur le contenu (`ftyp`), pas sur le type annoncé. Les messages vocaux de Discuss (mp3) sont lus par
  l'application.
- **Pièces jointes :** téléchargées seulement depuis leur conversation, par un membre (404 sinon, même pour
  l'identifiant d'une pièce jointe d'une autre conversation). Les autres pièces jointes (images, fichiers) ne
  sont pas encore affichées : `attachment_count` permet à l'application de le signaler.
- Un membre qui quitte une relation n'a plus accès à sa conversation.

## API (`/api/social/v1`, clé de portée `social_mobile`, membres du réseau)

| Méthode | Chemin | Corps / paramètres | Réponse |
|---|---|---|---|
| `GET` | `/chats` | | `{"chats": [...]}`, du plus récent au plus ancien |
| `POST` | `/chats` | `{"user_id"}` | Ouvre ou retrouve le chat à deux : `{"chat"}` ; `403 refused` (politique de contact, blocage) |
| `GET` | `/chats/<id>` | | `{"chat"}` |
| `GET` | `/chats/<id>/messages` | `before`, `after`, `limit` (50, 200 max) | `{"messages": [...]}` du plus ancien au plus récent |
| `POST` | `/chats/<id>/messages` | `{"body"}` | `{"message"}` ; `403` si bloqué ou vide |
| `POST` | `/chats/<id>/voice` | `{"data"}` : `.m4a` en base64 | `{"message"}` ; `403` si bloqué, trop long ou format refusé |
| `POST` | `/chats/<id>/attachments` | `{"data", "name", "body"?}` : fichier en base64, légende facultative | `{"message"}` ; `403` si bloqué, vide, de plus de 15 Mo, d'un type refusé (SVG, HTML, JavaScript, XML) ou image illisible |
| `GET` | `/chats/<id>/attachments/<att_id>` | `thumb=1` : miniature JPEG de 512 px au plus d'une image | Contenu de la pièce jointe (`Content-Type` d'origine) |
| `POST` | `/chats/<id>/read` | `{"last_message_id"}` | Marque comme lu jusqu'à ce message |
| `GET` | `/chats/unread` | | `{"unread"}` : total des non-lus |

Conversation : `{"id", "kind": "chat"|"relation", "title", "other_user_id", "relation_id", "unread",
"last_message", "last_activity"}`. Message : `{"id", "author_user_id", "author_name", "is_mine", "body", "date", "voice", "attachments", "attachment_count"}`, où
`voice` vaut `{"attachment_id", "mimetype"}` pour un message vocal, sinon `null`.
Une conversation dont on n'est pas membre répond `404`, sans dire si elle existe.

## Photos et fichiers

Un message porte `attachments` : `[{"id", "name", "mimetype", "size", "is_image"}]`, ses pièces jointes autres
que le message vocal, qu'elles viennent de l'application ou de Discuss sur le site (`attachment_count` reste
pour les versions installées). Le type d'un fichier envoyé vient de son contenu, jamais de l'appareil. Une
photo (JPEG, PNG, WebP) est redressée d'après son orientation EXIF, réduite à 4096 px et **réenregistrée sans
métadonnées** : une photo de téléphone porte sa position GPS exacte, alors que l'application ne montre jamais
qu'une zone d'environ 2 km. SVG, HTML, JavaScript et XML sont refusés : ouverts dans Discuss, ils exécuteraient du
code chez les autres membres (l'envoi se fait en sudo, le garde-fou SVG d'Odoo ne joue pas).
