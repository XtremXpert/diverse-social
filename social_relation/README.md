# Social Relations

Relations de **deux personnes ou plus** (couple, trouple, polycule). Chaque membre garde son compte et son profil,
peut rencontrer seul, et peut faire partie de **plusieurs relations**.

## Règles

- **Création :** un membre du réseau crée la relation ; il en est le premier membre.
- **Entrée :** un membre propose une personne. Si d'autres membres sont déjà là, **tous doivent approuver** la
  proposition ; un seul refus l'annule. La personne reçoit ensuite l'invitation et l'accepte ou la refuse.
  On ne peut pas inviter quelqu'un qui bloque un membre (ou est bloqué par lui), ni une personne hors du réseau.
- **Activation :** dès deux membres, la relation est active : conversation de groupe Discuss, et liens à deux
  (`res.partner.relation`, type symétrique choisi, « Partenaire » par défaut) entre chaque paire de membres. Un lien
  existant est réutilisé ; les cercles « Partenaires » de `social_circles` suivent.
- **Visibilité :** une relation n'est visible des autres membres que si **chacun** de ses membres l'accepte. Une
  nouvelle personne arrive en mode discret, ce qui recache la relation jusqu'à son accord. Un blocage entre un
  membre et un visiteur la cache à ce visiteur.
- **Départ :** un membre peut partir à tout moment ; ses liens à deux issus de la relation sont archivés (sauf
  s'ils servent à une autre relation) et il quitte la conversation. Sous deux membres, la relation est dissoute.

Les membres n'ont qu'un accès en lecture direct à leurs relations ; tout changement passe par les méthodes
`action_*`, qui vérifient l'appartenance. Les modérateurs gèrent les relations dans Réputation → Relations.

## API (`/api/social/v1`, clé de portée `social_mobile`)

| Méthode | Chemin | Corps | Effet |
|---|---|---|---|
| `GET` | `/relations` | | Mes relations (membre ou invité) |
| `POST` | `/relations` | `{"name", "description"?}` | Crée une relation |
| `GET` | `/relations/<id>` | | Une de mes relations, ou une relation visible |
| `PATCH` | `/relations/<id>` | `{"name"?, "description"?, "image_base64"?}` | Modifie le profil (5 Mo max) |
| `GET` | `/relations/<id>/image` | | Photo (512 px) |
| `POST` | `/relations/<id>/invite` | `{"user_id"}` | Propose une personne |
| `POST` | `/relations/<id>/members/<member_id>/approve` · `/reject` | | Approuve ou refuse une proposition |
| `POST` | `/relations/<id>/accept` · `/decline` | | L'invité répond |
| `POST` | `/relations/<id>/leave` | | Quitter |
| `POST` | `/relations/<id>/share` | `{"share": true\|false}` | Mon accord pour que la relation soit visible |
| `GET` | `/users/<user_id>/relations` | | Relations visibles d'un membre (jamais ses relations discrètes) |

Réponse : `{"relation": {"id", "name", "description", "state", "is_visible", "has_image", "my_state", "my_share",
"members": [{"member_id", "user_id", "name", "state", "share_publicly", "approved_by_me"}]}}`. Les noms sont les
pseudonymes quand ils existent ; un non-membre ne voit que les membres actuels, sans leurs réglages.
