# Social Nearby

Grille de proximité de l'application mobile.

## Vie privée

- L'application envoie sa position (`POST /position`), mais Odoo **ne garde que le centre de la case** d'environ
  550 m × 550 m qui la contient. La position exacte n'est jamais enregistrée.
- Une seule ligne par membre, écrasée à chaque envoi : **aucun historique**. `DELETE /position` l'efface ; elle
  l'est aussi après 7 jours sans nouvelles.
- Les distances sont données **par paliers** (« < 1 km », « 1–2 km », « 2–5 km », « 5–10 km », « 10–25 km »,
  « 25–50 km »…), calculées entre cases : la trilatération ne peut pas descendre sous la taille d'une case.
- L'activité est donnée par paliers aussi (`now` < 15 min, `today`, `week`), jamais l'heure exacte.
- **Réciprocité :** pour voir la grille, il faut partager sa propre position.

## Qui apparaît

Un membre du réseau qui partage sa position depuis moins de 7 jours, dans le rayon demandé (50 km par défaut,
200 au plus), et :

- dont le profil est terminé (`onboarding_done`) ;
- qui n'est ni banni ni « shadow banned » ;
- sans blocage avec le visiteur, dans un sens ou dans l'autre ;
- dont le profil est visible de tous les membres, ou du visiteur s'il est réservé aux connexions.

L'âge, le genre, l'orientation et la photo ne sont donnés que si le profil montre ses informations détaillées
au visiteur (`can_see_detailed_info` : tous les membres, cercles, cercle précis, connexions ou personne).

Les **relations visibles** (voir `social_relation`) dont au moins un membre est dans la grille ont leur propre
tuile, à la distance du membre le plus proche.

## API (`/api/social/v1`, clé de portée `social_mobile`, membres du réseau seulement)

| Méthode | Chemin | Corps | Réponse |
|---|---|---|---|
| `POST` | `/position` | `{"latitude", "longitude"}` | `{"shared": true}` |
| `DELETE` | `/position` | | `{"shared": false}` |
| `GET` | `/nearby?radius_km=50` | | `{"people": [...], "relations": [...]}` ; `409 no_position` si je ne partage pas ma position |
| `GET` | `/users/<id>/photo` | | Photo de profil, si le profil la montre au visiteur |

Tuile d'une personne : `{"user_id", "name", "distance", "last_seen", "availability", "detailed", "has_photo",
"age"?, "gender"?, "orientation"?}`. Tuile d'une relation : `{"id", "name", "distance", "has_image", "member_ids"}`.
