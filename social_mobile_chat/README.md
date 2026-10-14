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
- **Texte seul :** le corps est envoyé et rendu en texte brut (aucun HTML interprété), 4000 caractères au plus.
- Un membre qui quitte une relation n'a plus accès à sa conversation.

Pas encore de notification iPhone native : l'application relève les messages pendant qu'elle est ouverte.

## API (`/api/social/v1`, clé de portée `social_mobile`, membres du réseau)

| Méthode | Chemin | Corps / paramètres | Réponse |
|---|---|---|---|
| `GET` | `/chats` | | `{"chats": [...]}`, du plus récent au plus ancien |
| `POST` | `/chats` | `{"user_id"}` | Ouvre ou retrouve le chat à deux : `{"chat"}` ; `403 refused` (politique de contact, blocage) |
| `GET` | `/chats/<id>` | | `{"chat"}` |
| `GET` | `/chats/<id>/messages` | `before`, `after`, `limit` (50, 200 max) | `{"messages": [...]}` du plus ancien au plus récent |
| `POST` | `/chats/<id>/messages` | `{"body"}` | `{"message"}` ; `403` si bloqué ou vide |
| `POST` | `/chats/<id>/read` | `{"last_message_id"}` | Marque comme lu jusqu'à ce message |
| `GET` | `/chats/unread` | | `{"unread"}` : total des non-lus |

Conversation : `{"id", "kind": "chat"|"relation", "title", "other_user_id", "relation_id", "unread",
"last_message", "last_activity"}`. Message : `{"id", "author_user_id", "author_name", "is_mine", "body", "date"}`.
Une conversation dont on n'est pas membre répond `404`, sans dire si elle existe.
