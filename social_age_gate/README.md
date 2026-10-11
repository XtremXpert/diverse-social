# Vérification d'âge (18+)

Ce module demande à chaque membre de confirmer qu'il a 18 ans ou plus avant d'entrer dans le réseau social privé.

## Fonctionnement

- Le profil social reçoit le champ **Age verification (18+) passed**, faux par défaut. Il ne passe à vrai que sur une confirmation explicite du membre, jamais d'après l'année de naissance seule.
- La page `/age-verify` affiche une case à cocher obligatoire et une année de naissance facultative. L'envoi est refusé sans la case, si l'année est antérieure à 1900 ou si l'âge calculé est inférieur à 18 ans.
- Une fois la vérification passée, l'année saisie est enregistrée sur le profil. Le membre est envoyé vers `/onboarding` si son accueil n'est pas terminé, sinon vers `/web`.
- Un membre non vérifié qui visite `/my` ou `/my/home`, ou qui tente de passer l'accueil (`/onboarding/skip`), est redirigé vers `/age-verify`.
- Dans l'assistant d'accueil, une étape « Age verification (18+) » s'insère entre « about » et « preferences » si le profil n'est pas encore vérifié.

## Installation

À l'installation, un hook marque comme vérifiés les profils existants dont l'année de naissance indique 18 ans ou plus. Les profils sans année de naissance restent à vérifier.

## Accès et limites

- Les autres routes du portail ne sont pas interceptées : un membre non vérifié qui ouvre directement une autre page n'est pas redirigé.
- Un utilisateur sans profil social qui ouvre `/age-verify` est renvoyé vers `/web`.
- Les textes du module sont en anglais, avec une traduction `fr_CA`.

## Dépendances et tests

Dépend de `social_onboarding`. Les tests couvrent le champ, le hook d'installation, l'assistant et les routes du portail. Le parcours E2E `tests/e2e/test_15_age_gate.py` couvre la page.

```sh
odoo-dev test social_age_gate test_db
make test-e2e
```
