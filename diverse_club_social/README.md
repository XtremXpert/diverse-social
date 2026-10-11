# Diverse — Club Social

Module « feuille » du site www.diverse-cite.com : il installe l'ensemble des modules sociaux, d'adhésion, d'événements et de confidentialité, puis applique la configuration propre au site.

## Fonctionnement

- `/my` et `/my/home` redirigent vers `/my/dashboard`, après les contrôles de vérification d'âge (`/age-verify`) et d'accueil (`/onboarding`).
- `/my/dashboard` affiche un tableau de bord à la charte Diverse-Cité : statistiques de la semaine, activité récente, état d'adhésion et bloc « Mon compte ».
- `/community` (membres connectés) est une page de liens vers les sections du réseau social.
- `/partners` et `/partners/hosting` sont des pages publiques avec un formulaire de demande de partenariat et de demande de soumission d'hébergement.
- `/terms` est une page « Conditions d'utilisation » ; la page d'accueil du site est remplacée par un contenu bilingue.
- Le module renomme en français plusieurs vues du portail, ajoute des icônes aux cartes standard du portail et regroupe les menus backend de l'app **Social** en Discovery, Safety, Content et Community.
- Quand une adhésion devient active, les parrainages `pending_payment` du membre passent à l'état actif.

## Configuration appliquée à l'installation

Le `post_init_hook`, rejoué par les migrations, est idempotent. Il active le français (Canada) par défaut, nomme chaque site « Diverse-Cité », répare une racine de menu orpheline et range la navigation en trois conteneurs : Communauté, Mon réseau, Mon compte. Il traduit les menus, réserve les menus non publics au groupe `social_base.group_social_user` et pose le logo et le favicon de `theme_diverse_cite`.

Il fixe aussi le nom de communauté et la charte de `social_help`.

## Résumé hebdomadaire

Le cron **Diverse: Weekly email digest** s'exécute tous les 7 jours. Il crée une notification par profil admissible, puis envoie un courriel si le membre l'accepte (`digest_email_enabled`). Ne reçoivent le résumé que les profils dont l'accueil est fait, l'âge vérifié et l'utilisateur actif et non partagé (`share = False`). L'expéditeur vient du paramètre `diverse_club_social.digest_from_email`.

## Accès et limites

Les demandes de partenariat et d'hébergement sont lisibles par les utilisateurs internes et modifiables par le groupe Système. Le module ne fournit pour elles ni vue ni menu backend. Le courriel de confirmation des demandes de partenariat n'est pas implémenté (TODO dans le code).

## Dépendances et tests

Les dépendances sont nombreuses (voir `__manifest__.py`), dont `theme_diverse_cite` et `diverse_website_members_only`. Les tests unitaires couvrent le résumé hebdomadaire :

```sh
odoo-dev test diverse_club_social test_db
```

Les parcours E2E (par exemple `tests/e2e/test_24_digest.py`) sont lancés par `make test-e2e`.
