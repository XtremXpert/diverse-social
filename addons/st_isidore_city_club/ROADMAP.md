# Roadmap — Réseau citoyen St-Isidore-de-Beauce

Objectif : livrer une alternative locale à Facebook pour les ~850 résidents de
St-Isidore-de-Beauce (G0S 2S0). Inscription ouverte avec vérification de
résidence par modérateur, adhésion gratuite à vie, contenu communautaire +
gouvernance citoyenne, PWA mobile + notifications.

Stack : Odoo 19.0 Community + modules `social_*` / `club_*` existants,
assemblés par les deux nouveaux modules `city_club` (générique) et
`st_isidore_city_club` (leaf).

---

## Modules retenus / écartés

| Module | Statut | Pourquoi |
|---|---|---|
| `city_club` *(nouveau)* | ✅ | Vérification de résidence + helper postal + activation membership |
| `st_isidore_city_club` *(nouveau)* | ✅ | Leaf assembleur + config G0S + démo |
| `social_base`, `social_feed`, `social_search` | ✅ | Posts, fil, recherche |
| `social_group`, `social_story`, `social_gallery` | ✅ | Contenu communautaire |
| `social_messaging`, `social_notifications` | ✅ | Messages privés + cloches |
| `social_safety`, `social_circles` | ✅ | Blocage/silence + cercles (famille/voisins/village/public) |
| `social_discovery` | ✅ | Carte des membres centrée sur le village |
| `social_events`, `club_event_user` | ✅ | Évènements communautaires |
| `social_governance` | ✅ | Propositions + votes citoyens |
| `social_analytics` | ✅ | Tableau de bord modérateurs |
| `social_onboarding` | ✅ | Premier login guidé |
| `social_pwa` | ✅ | App installable + push |
| `social_privacy` | ✅ | Conformité Loi 25 |
| `club_membership` | ✅ | Activation de `group_social_user` via type gratuit |
| `club_social_profile_bdsm` | ❌ | Spécifique communauté adulte |
| `social_age_gate`, `social_calling`, `social_negotiation`, `social_consent` | ❌ | Workflows BDSM |
| `club_membership_sale`, `club_membership_website` | ❌ | Pas de paiement |
| `club_event_combo`, `event_lodging`, `club_payment_notice` | ❌ | Hors scope |

---

## Phase 1 — Foundation + résidence + Loi 25 (2 semaines)

**Objectif** : un résident peut s'inscrire, soumettre son code postal, être
approuvé par un modérateur, et accéder au réseau. Politique de confidentialité
publiée avant la collecte du premier code postal.

- [x] Module `city_club` — modèle + helper + action modérateur (livré)
- [x] Module `st_isidore_city_club` — config + type d'adhésion résident (livré)
- [ ] Installer dans une DB de test : `odoo-dev update st_isidore_city_club`
- [ ] Vérifier le flow de bout en bout (signup → submit → approve → group)
- [ ] Controller `/residency/verify` dans **`city_club`** (le workflow est
  générique, pas spécifique St-Isidore). Un seul item — pas deux : le
  controller gère **à la fois** le rendu du formulaire et la redirection
  d'un utilisateur sans groupe `group_social_user` qui essaie d'accéder
  ailleurs. Décorateur partagé sur les routes sociales.
- [ ] Notification modérateur à la soumission (`club_social_profile.notification._notify`
  vers tous les `group_social_moderator`)
- [ ] Rédiger politique de confidentialité Loi 25 — collecte code postal, droits
  d'accès, suppression. Activer le wizard `privacy_consent` à la première
  connexion.
- [ ] Tests Playwright : signup résident + approbation modérateur + accès feed
- [ ] Compte admin + 2 comptes modérateur initiaux (élus, comité loisirs)

**Sortie de phase** : un humain peut s'inscrire et accéder au réseau en moins de
24 h après approbation. Aucun code postal collecté sans politique active.

---

## Phase 2 — Groupes locaux + feed (1 semaine)

**Objectif** : les résidents trouvent immédiatement des espaces qui leur
parlent et y publient.

- [ ] Importer les 7 groupes démo en production (loisirs, école, fabrique,
  brigade, petites annonces, aînés, conseil municipal) avec créateurs/admins
  réels assignés
- [ ] Recruter 1 ambassadeur par groupe (élu, prof, bénévole) qui s'engage à
  3 posts/semaine pendant le lancement
- [ ] Catégories de posts via tag : `annonce`, `question`, `entraide`,
  `événement`, `alerte` (probable petit module `st_isidore_post_tags` ou
  configuration de `social_base.post` si le champ existe)
- [ ] Règles de modération affichées sur chaque groupe (`social_group.rule`)
- [ ] Cron de modération a posteriori : alerter modérateurs si un post >5
  signalements (existe déjà dans `club_social_moderation`)
- [ ] Mini-FAQ portail : "Comment publier", "Comment signaler", "Charte"

**Sortie de phase** : 7 groupes vivants avec au minimum 1 post/jour cumulé.

---

## Phase 3 — Discovery géo + évènements (1 semaine)

**Objectif** : voir qui habite près de chez moi (opt-in) et quels évènements
ont lieu cette semaine.

- [ ] Vérifier que `social_discovery` géocode bien `profile.city + region` en
  pré-remplissant les profils approuvés avec `city='St-Isidore-de-Beauce'`,
  `region='Québec'`
- [ ] Centrer la carte sur l'église (lat 46.3478 / lng -70.9836, déjà configuré)
- [ ] Tile provider OSM (vérifier `social_discovery` exposes ce paramètre,
  sinon ajouter un `ir.config_parameter`)
- [ ] Filtres : "à pied (1 km) / village (3 km) / municipalité (8 km) / Beauce"
- [ ] `social_events` : créer la catégorie d'évènement par défaut "Communauté
  St-Isidore", marqueur géo sur les évènements
- [ ] Évènements démo : Fête nationale 24 juin, marché Noël, AGA fabrique
- [ ] Calendrier portail `/events` épinglé dans la navigation principale

**Sortie de phase** : un nouveau membre voit sur sa carte 5+ voisins ayant
opté pour la visibilité, et 3+ évènements à venir.

---

## Phase 4 — Gouvernance citoyenne (1-2 semaines)

**Objectif** : permettre aux résidents de proposer et voter sur des sujets
communautaires. Distinct de la décision municipale officielle, mais utile
au conseil pour mesurer le pouls.

- [ ] Définir les catégories de propositions : `voirie`, `loisirs`,
  `environnement`, `budget_participatif`, `vie_communautaire`,
  `consultation_municipale`. Charger via `social_governance.category` en
  données spécifiques au leaf
- [ ] Workflow voté : proposition → discussion 7 j → vote 7 j → résolution
  (valeurs par défaut sur `social_governance.proposal.voting_closes_at`)
- [ ] Quorum minimal (config) : 30 votes pour valider une proposition
- [ ] Page publique `/governance/results` (lecture libre, votes anonymisés)
- [ ] Hook : à la clôture, notification automatique au conseil municipal
  (mail.alias dédié)
- [ ] Document : protocole d'engagement du conseil municipal envers les
  propositions ayant atteint le quorum
- [ ] Démo : 3 propositions tests (ex: "Achat d'une zamboni", "Compostage
  collectif", "Trottoir rang St-Joseph")

**Sortie de phase** : 1+ proposition réelle débattue et close avec quorum
atteint.

---

## Phase 5 — PWA + notifications + lancement (1 semaine + continu)

**Objectif** : utilisable depuis le téléphone comme une vraie app, avec
notifications push pour les contenus importants. Lancement public.

- [ ] Installer `social_pwa` + tester l'installation sur Android (Chrome)
  et iOS (Safari)
- [ ] Icônes + splash spécifiques St-Isidore (logo communauté)
- [ ] Notifications push : nouvelle proposition en vote, alerte brigade
  (signalement urgent), message privé
- [ ] Digest hebdomadaire courriel : top posts, évènements à venir,
  propositions en vote (réutiliser le pattern `diverse_club_social.cron_send_weekly_digest`,
  adapter le template à St-Isidore)
- [ ] Canal "alertes urgentes" (groupe Brigade incendie déjà créé) + push
  inconditionnel sur abonnés (panne d'eau, fermeture chemin, météo)
- [ ] **Communication papier** : flyer dans chaque boîte aux lettres
  (~400 portes) avec QR code → `/auth/signup`
- [ ] Annonce au feuillet paroissial + journal municipal
- [ ] Soirée de lancement physique au sous-sol de l'église : installation
  assistée + premières démos
- [ ] **Métriques de croissance** : inscriptions/jour, taux de complétion
  onboarding, DAU/MAU, ratio posts/membre/semaine. Tableau de bord interne
  via `social_analytics`
- [ ] Modération initiale renforcée : 1 modérateur d'astreinte par 24 h
  les 2 premières semaines

**Sortie de phase** : 100+ membres vérifiés au 30e jour, 30+ DAU.

---

## Décisions architecturales clés

1. **`group_social_user` reste ancré dans `club_membership`** — l'approbation de
   résidence crée une `membership` gratuite à vie qui appelle
   `action_activate()` → workflow standard `_sync_social_access()`. Aucune
   exception au pattern documenté dans `CLAUDE.md`.

2. **Pas d'adhésion payante** — exit `club_membership_sale` et
   `club_membership_website`. Les modules pourront être ajoutés plus tard
   si la municipalité veut une cotisation symbolique.

3. **Postal code + prefix sont configurés via `ir.config_parameter`** — pas
   en dur. Permet d'élargir/restreindre sans redéploiement et de décliner
   `city_club` pour d'autres villages.

4. **Visibilité par défaut sur la carte = OFF** (`show_on_map=False` dans
   `social_discovery`) — opt-in conscient, jamais une surprise. Loi 25.

5. **Vie privée du vote = anonyme**, mais quorum public. Modérateurs voient
   l'agrégat, pas le détail nominatif.

---

## Post-roadmap — pistes après v1

- Marketplace local (intégrer un module `social_marketplace`)
- Intégration calendrier paroissial / municipal via iCal feed
- Vidéo "tour du village" sur la page d'accueil
- Sondage flash hebdomadaire (mini-gouvernance)
- Pont avec le site municipal officiel (SSO si la municipalité a un système
  d'identification citoyenne)
- Déclinaisons : `frampton_city_club`, `st_lazare_city_club`… → preuve que
  `city_club` mérite son existence en tant que module générique
