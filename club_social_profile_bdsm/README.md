# Profil social — BDSM

Ajoute au profil de membre (`club_social_profile.profile`) un rôle BDSM, une expérience, des limites et une liste d'intérêts (kinks), puis calcule un score de compatibilité entre deux profils.

## Utilisation

- Le membre remplit sa section à **/my/profile/bdsm** : rôle, expérience, limites souples et limites strictes. La page est accessible par le menu du site **BDSM Profile** et par l'entrée de portail **Profil BDSM**.
- Il ajoute des intérêts avec un niveau : curieux, oui souple, oui ou expert. Un intérêt n'apparaît qu'une fois par profil ; le rajouter met son niveau à jour.
- Un intérêt absent de la liste peut être demandé ; la demande est créée à l'état « en attente ».
- Le profil public affiche le rôle, l'expérience et les intérêts. Les limites n'y sont pas affichées.
- Sur le profil d'un autre membre, un widget appelle l'API de compatibilité et affiche le score, le détail rôles/intérêts et les intérêts en commun.

## Compatibilité

Le score total vaut 65 % du score d'intérêts et 35 % du score de rôles. Le score d'intérêts est la part d'intérêts partagés, rapportée à la plus longue des deux listes (50 si aucun intérêt). Le score de rôles vient d'une table de paires (par exemple dominant/soumis = 100) ; 50 si un rôle manque, 40 pour une paire inconnue.

## Administration

- Menu **Social → BDSM → Kinks** : la liste des intérêts. Le module en fournit 43.
- Menu **Social → BDSM → Kink Requests** : les demandes en attente, avec **Approve** (crée l'intérêt, ou réutilise celui qui a le même nom) et **Reject** (motif obligatoire).
- API JSON (utilisateur connecté) : `GET /social/api/kinks`, `POST /social/api/kinks/request`, `POST /social/api/profile/kinks`, `GET /social/api/profile/<id>/compatibility`.

## Accès et limites

Les routes du portail et de l'API passent en `sudo` et se limitent au profil de l'utilisateur connecté. Les droits d'écriture sur les intérêts et les demandes vont aux administrateurs sociaux et au groupe Système. Les boutons Approve/Reject sont réservés aux modérateurs, mais le fichier de droits ne donne pas d'accès aux demandes à ce groupe ; un modérateur qui n'est pas administrateur pourrait donc être bloqué.

## Dépendances et tests

Dépend de `club_social_profile` et de `portal`. Les tests unitaires couvrent le calcul de compatibilité, les demandes et les routes du portail et de l'API :

```sh
odoo-dev test club_social_profile_bdsm test_db
```

Le parcours E2E `tests/e2e/test_16_bdsm.py` est lancé par `make test-e2e`.
