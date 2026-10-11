# Invitations sociales

Inviter quelqu'un à un groupe ou à un cercle depuis sa fiche, ou par courriel. Le module se greffe sur les modules sociaux existants sans les modifier.

## Fonctionnement

- Sur la fiche publique d'un membre, le bouton « Inviter… » liste mes groupes où j'ai le droit d'inviter et, si la personne est une de mes connexions, mes cercles. Les groupes et cercles dont elle est déjà membre sont exclus. Le choix crée une invitation dans le site, que la personne accepte ou non.
- La route `POST /invite/email` reçoit un courriel et un groupe ou un cercle :
  - si le courriel est celui d'un membre, l'invitation est créée dans le site et aucun courriel n'est envoyé ;
  - sinon, l'intention est enregistrée (`social_invitations.pending`) et une invitation d'inscription est envoyée par le parrainage de `social_reputation`.
- La réponse est toujours la même (« invitation envoyée »), que la personne soit membre, inconnue ou bloquée : l'inviteur n'apprend pas qui est déjà inscrit.
- À la création d'un utilisateur dont l'identifiant correspond au courriel, les invitations en attente deviennent des invitations dans le site. Rien n'est ajouté sans acceptation.
- Une intention expire après 30 jours. Le cron quotidien **Social Invitations: expirer les intentions** les marque expirées.

## Accès et limites

- Réservé aux membres (`social_base.group_social_user`). Un blocage (`social_safety`) empêche l'invitation.
- Un cercle n'accepte que des connexions acceptées, y compris par courriel. Seul le propriétaire du cercle invite.
- Les doublons et les erreurs sont ignorés sans casser la requête.
- Les intentions sont gérées par les modérateurs et les administrateurs.
- Aucun formulaire du module n'appelle `/invite/email` : la route existe, mais il faut l'appeler depuis une autre page.

## Dépendances et tests

Dépend de `club_social_profile`, `social_group`, `social_circles`, `social_safety` et `social_reputation`. Le module n'a pas de tests unitaires. Le parcours E2E `tests/e2e/test_32_invite_hub.py` couvre le bouton et l'invitation par courriel :

```sh
make test-e2e
```
