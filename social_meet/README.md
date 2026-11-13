# Social Meet

Rencontres de l'application mobile : **spontanées** (`kind = now`) et **planifiées**
(`kind = planned`), avec plusieurs participants dans les deux cas.

- Modèle `social_meet.meet` : hôte (éventuellement au nom d'une relation), fenêtre,
  lieu approché (case ≈ 550 m ou Safe Zone), audience (`nearby`, `connections`,
  `circles`, `invited`), places, participants, fil (`channel_id`) et événement enrobé
  (`event_id`, réservé au mode planifié).
- Modèle `social_meet.participant` : hôte et invités, un seul enregistrement par
  membre et par rencontre.
- Cron horaire : les rencontres dont la fenêtre est passée passent à `expired`.

Spécification : `docs/spec-rencontres.md` du dépôt diverse-odoo.

## Limites de ce premier slice

- Pas encore d'API `/api/social/v1/meets` (contrôleur à venir, tâche 17).
- Pas encore de fil `discuss.channel` de type `meet` ni d'enrobage `event.event`
  (tâches 18 et 17) : les champs existent mais restent vides.
- Tests écrits mais pas encore exécutés dans une base.
