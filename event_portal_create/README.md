# Événements — création portail (`event_portal_create`)

Permet aux membres **portail** appartenant au groupe **« Organisateur portail (événements) »**
de créer, modifier, publier et supprimer **leurs propres** événements depuis le
portail/site (`/my/events`), **sans aucun accès au backend Odoo**.

## Comment autoriser un membre à organiser

1. Backend Odoo → **Paramètres → Utilisateurs** → ouvrir l'utilisateur portail.
2. Cocher le groupe **« Organisateur portail (événements) »**.
3. Le membre voit désormais la carte **« Mes événements »** dans son portail
   (`/my/home`) et peut gérer ses événements via `/my/events`.

## Ce que l'organisateur peut faire

- Créer un événement : nom, dates (dans son fuseau), description, nombre de
  places, **visibilité sociale** (tous les membres / cercles spécifiques —
  parmi ses propres cercles).
- Modifier / supprimer (si aucun inscrit) ses événements.
- **Publier / dépublier** : un événement est créé en **brouillon**
  (non publié) ; il n'apparaît sur `/event` qu'une fois publié.

## Sécurité

Le contrôleur est la **frontière de sécurité** : chaque route vérifie
l'appartenance au groupe, agit en `sudo()` avec une **liste blanche de champs**,
et restreint toute opération aux événements dont l'utilisateur est
l'organisateur (`organizer_user_id`). Aucune règle `ir.rule` n'est posée sur
`event.event` (pas d'effet de bord sur les autres modules événement) ; le
groupe n'accorde aucun accès backend.

## Dépendances

`social_events` (fournit `organizer_user_id` et `social_visibility`),
`website_event`, `portal`, `website`.
