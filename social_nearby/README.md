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

## Je veux rencontrer

Mode activé par le membre pour une durée **qu'il choisit** (1 à 12 heures, 3 par défaut), puis arrêté de lui-même.
Pendant ce temps :

- sa tuile porte `"meet": true`, passe **en tête de la grille** et reste « là maintenant » (`last_seen: now`) ;
- l'application signale ses déplacements **même fermée** (changements de position importants d'iOS, environ
  500 m), et seulement pendant ce mode ; hors de ce mode, la position n'est envoyée qu'application ouverte.

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
| `GET` | `/nearby?radius_km=50` | | `{"meet_until", "people": [...], "relations": [...]}` (`meet_until` : mon mode « Je veux rencontrer », ou `null`) ; `409 no_position` si je ne partage pas ma position |
| `POST` | `/meet` | `{"active": true, "hours": 3}` ou `{"active": false}` | `{"meet_until"}` (ou `null`) ; `400` durée hors de 1–12 ; `409 no_position` sans position |
| `GET` | `/users/<id>/photo` | | Photo de profil, si le profil la montre au visiteur |

Tuile d'une personne : `{"user_id", "name", "distance", "last_seen", "meet", "availability", "detailed", "has_photo",
"age"?, "gender"?, "orientation"?}`. Tuile d'une relation : `{"id", "name", "distance", "has_image", "member_ids"}`.
