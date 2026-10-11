# Consentement

Chaque membre peut définir une « porte de consentement » : une liste de conditions qu'un visiteur doit accepter, avec une demande que le membre approuve ou refuse.

## Fonctionnement

- Dans le menu de site **My Network → Consent** (`/my/consent`), le membre voit les demandes en attente et ses dernières demandes envoyées. Une carte « Consentement » s'affiche aussi sur `/my`, avec le nombre de demandes à traiter.
- Dans `/my/consent/gate`, il rédige une introduction, fixe un délai minimal d'examen en heures (24 par défaut), active ou désactive sa porte, et ajoute ou retire des conditions.
- Une condition est soit une case à cocher (« Acknowledgement »), soit une question ouverte. Chacune peut être obligatoire et avoir une indication.
- Le visiteur remplit la porte sur `/consent/gate/<id>`. La demande est soumise aussitôt; une condition obligatoire non cochée ou sans réponse bloque l'envoi.
- Le propriétaire approuve ou refuse sur `/consent/request/<id>`, avec une note facultative. L'approbation est refusée tant que le délai minimal n'est pas écoulé. Le demandeur peut retirer sa demande.
- Un visiteur ne peut avoir qu'une demande active (brouillon, soumise, en examen ou approuvée) par porte. Un profil n'a qu'une porte.
- Le back-office offre le menu **Consent** : My Gate, Requests Inbox, Sent Requests et, pour les modérateurs, Administration.

## Accès et limites

- Les membres (`social_base.group_social_user`) voient leur porte, les portes actives et les demandes dont ils sont demandeur ou destinataire.
- Les modérateurs peuvent examiner toutes les demandes.
- Le module enregistre le statut de consentement (`get_consent_status_for`), mais aucun autre module ne s'en sert pour bloquer un contact. Aucune page de profil ne renvoie vers `/consent/gate/<id>`.
- L'option « Require all acknowledgements » est enregistrée, mais le code ne l'applique pas : seule l'option « obligatoire » de chaque condition compte.
- `_notify_consent_received` est un point d'extension vide : aucune notification n'est envoyée.

## Dépendances et tests

Dépend de `social_base` et `club_social_profile`. Le parcours E2E `tests/e2e/test_05_safety_consent.py` (`make test-e2e`) couvre aussi `/my/consent`. Pour lancer les tests du module :

```sh
odoo-dev test social_consent test_db
```
