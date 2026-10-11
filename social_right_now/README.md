# Disponible maintenant

Un membre se déclare « disponible » pour une durée bornée. Pendant ce temps, n'importe quel membre peut lui écrire, même sans connexion.

## Fonctionnement

- La page `/right-now` (menu **My Network → Disponible maintenant**) affiche les sessions actives des autres membres.
- On active sa session pour 1 h, 2 h ou 4 h, avec une intention courte (120 caractères au plus). Réactiver relance la session existante : une seule session active par personne.
- On peut couper sa session à tout moment.
- Le tableau exclut soi-même, les personnes bloquées, les profils en mode panique et les profils shadow-bannis.
- « Écrire » ouvre une conversation Discuss. Une conversation nouvelle est liée à la session; une conversation préexistante ne l'est pas.
- Une session active est une exception à la politique de contact de `social_messaging_discuss`.
- À l'expiration, on ne peut plus écrire dans une conversation liée à la session, sauf si une connexion acceptée existe entre les deux membres. Les messages restent en place.
- La page décompte les minutes restantes et se recharge toutes les 60 secondes, sauf pendant une saisie.

## Configuration

Le cron **Right Now: expirer les sessions** tourne toutes les 15 minutes. Il diffuse un événement bus pour les sessions tout juste expirées. La fermeture des conversations ne dépend pas du cron.

## Accès et limites

- Pages réservées au groupe `social_base.group_social_user`. Un membre ne lit que sa propre session.
- Les modérateurs ont tous les droits et le menu back-office **Disponible maintenant**.

## Dépendances et tests

Dépend de `social_messaging_discuss`, `club_social_profile`, `social_safety` et `social_notifications`. Le module n'a pas de tests unitaires. Le scénario E2E `tests/e2e/test_30_right_now.py` s'exécute avec `make test-e2e`.
