# Négociation sociale

Document de négociation co-rédigé par deux membres connectés : limites, désirs, garde-fous, mot de sécurité et double signature.

## Fonctionnement

- Dans le portail, **My Network → Negotiations** (`/my/negotiation`) liste les documents de la personne. Une carte « Négociations » s'ajoute aussi à `/my`.
- On crée un document avec une connexion acceptée seulement (`club_social_profile.connection`). Un document à soi-même est refusé.
- L'initiateur ajoute ou retire des éléments tant que le document est en brouillon. Catégories : limite dure, limite douce, désir, garde-fou / aftercare, autre.
- Cycle : brouillon → partagé → en révision → actif → archivé. L'initiateur partage; la première réponse du partenaire passe le document en révision.
- Chaque partie répond à chaque élément (oui, peut-être, non, N/A) et peut laisser une note partagée.
- Le document devient actif quand les deux parties ont signé. Une signature n'est possible qu'une fois par personne.
- « Nouvelle version » copie le document et ses éléments en brouillon (version + 1) et archive l'original.
- Le score d'accord est le pourcentage d'éléments répondus par les deux où les deux réponses sont « oui » ou « peut-être ».

## Accès et limites

- Un membre (`social_base.group_social_user`) ne voit que les documents dont il est l'initiateur ou le partenaire. Il ne peut pas supprimer de document.
- Les modérateurs et administrateurs sociaux ont tous les droits et peuvent archiver n'importe quel document.
- Le back-office offre le menu **Negotiations → My Documents**.
- Le mot de sécurité est un champ texte ordinaire, masqué dans le formulaire. Le module ne le chiffre pas lui-même.

## Dépendances et tests

Dépend de `club_social_profile` et `portal`. Les tests couvrent le cycle de vie, les scores et le portail :

```sh
odoo-dev test social_negotiation test_db
```

Le scénario E2E `tests/e2e/test_13_negotiation_notifications.py` s'exécute avec `make test-e2e`.
