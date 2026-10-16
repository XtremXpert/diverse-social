# Guide des modules — Réseau social & Club

> Généré le 2026-05-17. Couvre tous les modules `social_*`, `club_*`, `website_blog_restricted` et `website_members_only`.

---

## Table des matières

1. [Couche de base](#1-couche-de-base)
2. [Profil membre](#2-profil-membre)
3. [Profil BDSM](#3-profil-bdsm)
4. [Fil d'actualité](#4-fil-dactualité)
5. [Stories](#5-stories)
6. [Galeries](#6-galeries)
7. [Groupes & Communautés](#7-groupes--communautés)
8. [Messagerie privée](#8-messagerie-privée)
9. [Cercles de confiance](#9-cercles-de-confiance)
10. [Découverte de profils](#10-découverte-de-profils)
11. [Sécurité personnelle](#11-sécurité-personnelle)
12. [Consentement d'accès](#12-consentement-daccès)
13. [Négociation](#13-négociation)
14. [Gouvernance communautaire](#14-gouvernance-communautaire)
15. [Réputation & parrainage](#15-réputation--parrainage)
16. [Notifications](#16-notifications)
17. [Intégration nouveaux membres](#17-intégration-nouveaux-membres)
18. [Vérification d'âge 18+](#18-vérification-dâge-18)
19. [Appels vidéo/audio](#19-appels-vidéoaudio)
20. [Modération](#20-modération)
21. [Analytique](#21-analytique)
22. [Confidentialité & Loi 25](#22-confidentialité--loi-25)
23. [Adhésions club](#23-adhésions-club)
24. [Events](#24-events)
25. [Website — Blog restreint](#25-website--blog-restreint)
26. [Website — Membres seulement](#26-website--membres-seulement)

---

## 1. Couche de base

**Module :** `social_base`

Primitives fondamentales du réseau social. Tous les autres modules en dépendent.

### Posts (`social_base.post`)
- Contenu HTML avec pièces jointes (photos, vidéos, mixte)
- Visibilité : `public` / `members` / `friends` / `private`
- États : `draft` → `published` → `archived` / `moderation`
- Compteurs : likes, commentaires, vues, partages
- Post épinglé (`is_pinned`)
- Workflow de modération : soumettre → approuver/rejeter avec raison

### Commentaires (`social_base.comment`)
- Commentaires sur les posts
- Réactions sur les commentaires

### Réactions (`social_base.reaction`)
- Réactions emoji sur posts, commentaires et stories
- Comptage des likes séparé

### API portail
- `POST /social/posts` — créer un post
- `PATCH /social/posts/<id>` — modifier
- `DELETE /social/posts/<id>` — supprimer
- `POST /social/posts/<id>/react` — réagir
- `POST /social/posts/<id>/comment` — commenter

---

## 2. Profil membre

**Module :** `club_social_profile`

Module pivot dont dépend l'ensemble de la stack sociale.

### Profil (`club_social_profile.profile`)
- Photo de profil (400×400) et photo de couverture (1200×400)
- Identité : pronoms, année de naissance, âge calculé, genre (7 options), orientation (8 options)
- Bio (texte libre) et citation (200 caractères max)
- Disponibilité : disponible / couple ouvert / couple fermé / pas disponible
- Langues parlées et intentions (looking for)
- Localisation : ville, région/province
- Pseudonyme stealth (affiché aux connexions plutôt que le login)
- Visibilité du profil : `members` (tous les membres) ou `connections` (connexions uniquement)
- Partage de lien profil activable/désactivable
- Résumé hebdomadaire par courriel activable/désactivable
- Compteur de vues du profil + historique des visites
- Vérification 18+ automatique basée sur l'année de naissance
- Contrainte : un seul profil par utilisateur, minimum 18 ans

### Connexions (`club_social_profile.connection`)
- Demandes de connexion avec états : `pending` → `accepted` / `declined`
- Bidirectionnel — acceptation des deux côtés

### Notifications (`club_social_profile.notification`)
- Notifications in-app avec type, corps et URL
- Envoi temps-réel via `bus.bus`

### Visites de profil (`club_social_profile.profile_visit`)
- Enregistrement des visites avec date

### Portail
- Page publique du profil
- Formulaire d'édition du profil
- Tableau de bord personnel
- Page de découverte

---

## 3. Profil BDSM

**Module :** `club_social_profile_bdsm`

Extension optionnelle du profil pour contextes BDSM/kink.

### Kinks (`club_social_profile_bdsm.kink`)
- Liste de kinks/intérêts gérée par les modérateurs
- Compteur du nombre de profils intéressés

### Niveaux d'intérêt (`club_social_profile_bdsm.kink_level`)
- Niveau par kink et par profil : `curious` / `soft yes` / `yes` / `expert`
- Un seul niveau par kink par profil

### Demandes d'ajout (`club_social_profile_bdsm.kink_request`)
- Les membres peuvent soumettre un nouveau kink à ajouter
- Workflow : `pending` → `approved` (crée le kink) / `rejected` (avec raison)
- Traçabilité du modérateur qui a traité la demande

### Portail
- Section BDSM intégrée dans la page de profil
- API kinks pour le portail

---

## 4. Fil d'actualité

**Module :** `social_feed`

Fil agrégé qui rassemble tous les types de contenu en une seule vue.

### Types de contenu agrégés
- Posts publiés (avec règles de visibilité)
- Stories actives des connexions
- Événements futurs (avec visibilité par cercles)
- Inscriptions à des événements par les connexions (RSVP sociaux)
- Propositions en cours de vote
- Photos approuvées dans les galeries publiques/membres

### Modes de tri
- **Chronologique** (`sort=recent`) — tri par date décroissante, défaut
- **Pertinence** (`sort=relevance`) — algorithme inspiré Hacker News :
  - Décroissance temporelle (demi-vie 24h, exposant 1.2)
  - Engagement (log-scale : likes + commentaires×2 + votes×3 + vues×0.1)
  - Affinité connexion : ×1.5 si l'auteur est une connexion acceptée
  - Boost par type : événements proches ×2, propositions qui ferment ×2, stories ×1.2

### Règles de visibilité des posts
- `public/members` → tous les membres
- `friends` → uniquement si l'auteur est une connexion acceptée
- `private` → uniquement l'auteur
- Posts de groupe → uniquement les membres du groupe
- Utilisateurs bloqués exclus automatiquement

### Transparence algorithmique
- Page portail `/social/feed/transparency` expliquant comment fonctionne le tri
- Extensible par héritage (`_get_feed_types`, `_get_feed_dispatch`)

---

## 5. Stories

**Module :** `social_story`

Stories éphémères de 24 heures style Instagram/Facebook.

### Features
- Photo ou vidéo (détection automatique via mimetype)
- Expiration automatique à 24h après création
- Suivi des vues : compteur + liste des utilisateurs ayant vu
- États : `active` / `expired` / `archived`
- Réactions (partagées avec `social_base.reaction`)
- Cron de nettoyage : suppression 7 jours après expiration
- Portail : liste et vue d'une story

---

## 6. Galeries

**Module :** `social_gallery`

Galeries photos/vidéos avec modération.

### Galeries (`social_gallery.gallery`)
- Titre, description, propriétaire, séquence
- Visibilité : `public` / `members` / `private`
- Galeries partagées : acceptent les soumissions de tous les membres
- Photo de couverture configurable
- Compteurs : total, approuvées, en attente

### Photos (`social_gallery.photo`)
- Image avec thumbnail automatique (512px)
- Workflow de modération : `pending` → `approved` / `rejected`
- Soumetteur et modérateur tracés avec date
- Photos des galeries partagées nécessitent approbation

### Portail
- Galerie publique avec filtres
- API galeries pour le portail

---

## 7. Groupes & Communautés

**Module :** `social_group`

Groupes thématiques avec niveaux de confidentialité.

### Groupes (`social_group.group`)
- Nom, description, image de groupe, image de couverture
- Confidentialité : `public` (visible et rejoignable par tous) / `private` (visible, adhésion par approbation) / `secret` (invisible aux non-membres)
- Mode d'adhésion : `open` / `approval` / `invite only`
- Modération des posts optionnelle (`require_moderation`)
- Rôles : créateur, administrateurs, modérateurs, membres
- Règles du groupe (liste ordonnée)
- Contrainte : le dernier administrateur ne peut pas quitter

### Demandes d'adhésion (`social_group.join_request`)
- États : `pending` → `approved` / `rejected`
- Traçabilité du modérateur, raison de rejet
- Cron : nettoyage des demandes traitées après 30 jours

### Posts dans les groupes
- Les posts peuvent être liés à un groupe (`group_id` sur `social_base.post`)
- Posts des groupes secrets visibles uniquement aux membres

---

## 8. Messagerie privée

**Module :** `social_messaging`

Messagerie directe entre deux membres.

### Fils (`social_messaging.thread`)
- Conversation entre deux participants
- Compteur de messages non lus

### Messages (`social_messaging.message`)
- Contenu texte + pièces jointes
- Statut de lecture par utilisateur (`read_by_ids`)
- Vérification au moment de l'envoi : impossible si l'un des deux a bloqué l'autre
- Envoi bloqué si un blocage existe dans n'importe quel sens

### Portail
- Interface de messagerie style chat
- API messagerie temps-réel

---

## 9. Cercles de confiance

**Module :** `social_circles`

Organisation des connexions en niveaux de confiance nommés.

### Cercles (`social_circles.circle`)
- Propriétaire, nom (traduit), description, séquence, couleur
- Membres : liste de `res.users`
- Compteur de membres
- Contrainte : nom unique par profil
- Méthodes : `add_member`, `remove_member`, `has_member`

### Types de relations
- Intégration avec `partner_multi_relation` (OCA) pour les types de relations entre partenaires
- Données initiales de types de relations prédéfinis

### Visibilité par cercle
- Extension du mixin de visibilité : contenu visible selon l'appartenance au cercle

### Portail
- Gestion des cercles sur le portail

---

## 10. Découverte de profils

**Module :** `social_discovery`

Recherche consentie de profils — l'utilisateur cherche, pas l'algorithme.

### Critères de recherche (`social_discovery.criteria`)
- Recherches nommées et sauvegardables
- Critère "par défaut" chargé automatiquement
- Filtres disponibles :
  - Âge min/max
  - Ville (correspondance partielle insensible à la casse)
  - Genre (sélection multiple)
  - Orientation (sélection multiple)
  - Disponibilité (sélection multiple)
  - Langues parlées (correspondance par intersection)
  - Intentions (looking for, par intersection)
  - Cercles uniquement (`in_circles_only`)
  - Accessibles uniquement (`reachable_only`) — exclut les profils avec un consent gate actif non approuvé

### Listes de valeurs
- `social_discovery.gender_value` — valeurs de genre pour les filtres
- `social_discovery.orientation_value` — valeurs d'orientation
- `social_discovery.availability_value` — valeurs de disponibilité

### Portail
- Page de liste des membres avec filtres
- API recherche

---

## 11. Sécurité personnelle

**Module :** `social_safety`

Contrôles de sécurité personnelle : bloquer, muter, mode panique.

### Blocage (`social_safety.block`)
- Bloquer un utilisateur (avec note privée optionnelle)
- Bidirectionnel : `is_blocked(A, B)` retourne `True` si A a bloqué B **ou** B a bloqué A
- Idempotent : `block_user` ne crée pas de doublon
- `get_blocked_ids_for` : retourne tous les IDs bloqués dans les deux sens
- Effet : exclut l'utilisateur du feed, bloque la messagerie, masque des découvertes

### Silencieux (`social_safety.mute`)
- Muter un utilisateur temporairement (avec date d'expiration) ou de façon permanente
- `is_muted` vérifie le mute actif (tient compte de la date d'expiration)
- Cron : expiration automatique des mutes temporaires

### Extension de la découverte
- Les profils bloqués sont automatiquement exclus des résultats de découverte

### Portail
- Page de gestion des blocages et mutes (`/my/safety`)

---

## 12. Consentement d'accès

**Module :** `social_consent`

Portail de consentement obligatoire avant de pouvoir contacter un profil.

### Portail de consentement (`social_consent.gate`)
- Activable/désactivable par profil
- Texte d'introduction personnalisé
- Délai minimum de révision (défaut : 24h) — le propriétaire ne peut pas approuver avant
- Option : tous les items doivent être cochés avant soumission
- Items du portail :
  - `check` — case à cocher avec texte et hint
  - `question` — question ouverte (réponse texte)
- Compteur de demandes en attente

### Demandes (`social_consent.request`)
- États : `submitted` → `under_review` → `approved` / `rejected`
- Intégration avec `social_discovery` : filtre `reachable_only` vérifie l'approbation

### Portail
- Formulaire de soumission de demande de consentement
- Gestion de ses propres demandes

---

## 13. Négociation

**Module :** `social_negotiation`

Documents de négociation co-rédigés entre deux personnes.

### Documents (`social_negotiation.negotiation`)
- Initiateur et partenaire (deux utilisateurs distincts)
- États : `draft` → `shared` → `reviewing` → `active` / `archived`
- Versionnement : création d'une nouvelle version archive automatiquement l'ancienne
- Mot de sécurité (safe word) stocké
- Co-signatures : date de signature de chaque partie, état `active` quand les deux ont signé
- Score d'accord : % d'items où les deux répondent `yes` ou `soft`

### Items (`social_negotiation.item`)
- Catégories : `hard_limit` / `soft_limit` / `desire` / `safeguard_aftercare` / `other`
- Réponse de chaque partie : `yes` / `soft` / `no (hard limit)` / `n/a`
- Note partagée sur l'item
- `is_compatible` : les deux ont répondu `yes` ou `soft`

### Sécurité
- Seuls les deux participants ou un modérateur peuvent agir
- Retrait impossible une fois accepté/rejeté

---

## 14. Gouvernance communautaire

**Module :** `social_governance`

Propositions, votes et journal des décisions de la communauté.

### Propositions (`social_governance.proposal`)
- Titre, description HTML, auteur, catégorie
- États : `draft` → `open` → `voting` → `accepted` / `rejected` / `withdrawn`
- Dates d'ouverture et de fermeture du vote
- Date d'implémentation (une fois acceptée)

### Votes (`social_governance.vote`)
- Choix : `yes` / `no` / `abstain`
- Un seul vote par membre par proposition (modifiable)
- Statistiques : total, oui, non, abstentions, % d'approbation (oui vs oui+non)

### Workflow
- Seul l'auteur ou un modérateur peut retirer une proposition
- Fermeture automatique : cron quotidien ferme les votes expirés (`voting_closes_at` dépassé)
- Résultat automatique : `accepted` si oui > non, sinon `rejected`

### Journal des décisions
- Enregistrement public des décisions prises (`social_governance.decision_log`)

### Portail
- Liste des propositions avec filtres par état
- Interface de vote

---

## 15. Réputation & parrainage

**Module :** `social_reputation`

Système de parrainage communautaire créant une chaîne de responsabilité.

### Parrainages (`social_reputation.vouching`)
- Sponsor → Newcomer avec déclaration textuelle
- États : `active` / `withdrawn`
- Contraintes :
  - Impossible de se parrainer soi-même
  - Pas de parrainage circulaire (si B a parrainé A, A ne peut pas parrainer B)
  - Retrait requiert une raison obligatoire
  - Retrait impossible par quelqu'un d'autre que le sponsor (sauf modérateur)
- Retrait traçable : date, raison, qui a retiré

### Extension de la découverte
- Intégration des parrainages dans les profils de découverte

### Portail
- Section parrainage sur les profils publics
- Page de gestion de ses parrainages

---

## 16. Notifications

**Module :** `social_notifications`

Notifications temps-réel pour toutes les activités sociales.

### Types de notifications (en plus des types de base du profil)
- `event_registration` — inscription à un événement
- `group_join_request` — demande d'adhésion à un groupe
- `group_join_approved` — adhésion approuvée
- `proposal_voting` — proposition ouverte au vote
- `story_new` — nouvelle story d'une connexion
- `gallery_photo_approved` — photo approuvée dans une galerie
- `gallery_photo_rejected` — photo rejetée
- `vouching_received` — parrainage reçu
- `vouching_withdrawn` — parrainage retiré
- `negotiation_shared` — document de négociation partagé
- `negotiation_signed` — document de négociation signé
- `negotiation_active` — document de négociation actif (les deux ont signé)
- `circle_added` — ajouté à un cercle

### Livraison temps-réel
- Envoi via `bus.bus` à la création de chaque notification
- Payload : id, type, corps, URL de destination

### Hooks
- Chaque module social dispose de son hook de notification (fichiers `*_hooks.py`)
- Architecture découplée : les hooks sont dans `social_notifications`, pas dans les modules sources

### Portail
- Cloche de notification dans l'en-tête
- Page dédiée des notifications (`/my/notifications`)
- API notifications pour marquer comme lu

---

## 17. Intégration nouveaux membres

**Module :** `social_onboarding`

Parcours guidé de complétion de profil pour les nouveaux membres.

### Assistant (`social_onboarding.wizard`)
- 4 étapes : Bienvenue → À propos → Préférences → Terminé
- Navigation avant/arrière et possibilité de sauter
- **Étape Bienvenue** : photo de profil
- **Étape À propos** : pronoms, bio, année de naissance, ville
- **Étape Préférences** : visibilité du profil, disponibilité, résumé hebdomadaire
- Validation : bloque si âge < 18
- Marquage `onboarding_done = True` à la fin
- Chargement de l'état actuel du profil à l'ouverture

### Hook d'adhésion
- Déclenchement automatique de l'onboarding lors de l'activation d'une adhésion

### Portail
- Accès via `/my/onboarding`
- Vue intégrée dans l'interface portail

---

## 18. Vérification d'âge 18+

**Module :** `social_age_gate`

Barrière obligatoire 18+ avant accès au réseau social.

### Champ supplémentaire
- `age_gate_passed` (booléen) ajouté au profil
- Passage automatique à `True` dès que `age_verified` est `True` (à la création ou à la mise à jour de `birth_year`)

### Wizard
- Interface portail de vérification d'âge
- Déclaration explicite du membre

### Portail
- Page de barrière d'âge (`/social/age-gate`)
- Redirection automatique si non vérifié

### Hook post-installation
- Configuration initiale via `post_init_hook`

---

## 19. Appels vidéo/audio

**Modules :** `social_calling_discuss`, `social_calling`

Appels entre membres par Discuss natif (WebRTC), relayés par le SFU d'Odoo quand il est configuré
(*Paramètres → Discuss → RTC Server URL*). Jitsi a été retiré.

- `social_calling_discuss` : bouton « Appeler » du profil, route `/discuss-call/<user_id>` (conversation
  privée Discuss, blocage mutuel vérifié), sonnerie chez l'appelé par le bus (`social_calling/incoming_call`).
- `social_calling` : service portail de présence et fenêtre d'appel entrant (sonnerie, Répondre, Refuser),
  type de notification « Appel manqué ».

---

## 20. Modération

**Module :** `club_social_moderation`

Bans, shadow bans et signalements pour les modérateurs de club.

### Bans (`club_social_moderation.ban`)
- Ban temporaire (avec date d'expiration) ou permanent
- Raison obligatoire
- Levée manuelle traçable (qui, quand)
- `is_active` calculé automatiquement (tient compte de l'expiration et de la levée)
- Cron d'expiration automatique des bans temporaires

### Shadow ban (`club_social_moderation.profile`)
- Extension du profil : `is_shadow_banned`
- Le membre shadow-banni voit ses propres contenus mais les autres ne les voient pas

### Signalements (`club_social_moderation.report`)
- Signalement d'un profil ou d'un contenu
- Raison et description
- États : `pending` → `resolved` / `dismissed`

---

## 21. Analytique

**Module :** `social_analytics`

Tableau de bord modérateur avec métriques globales.

### Tableau de bord (`social_analytics.analytics_dashboard`)
- Vue agrégée : engagement (posts, commentaires, réactions), adhésions nouvelles, modération, gouvernance, négociations, réputation, stories
- API JSON pour le portail modérateur
- Métriques sur une période configurable

---

## 22. Confidentialité & Loi 25

**Module :** `social_privacy`

Bridge entre les modules OCA de protection des données et les modules sociaux, pour la conformité à la Loi 25 (Québec).

### Responsable de la vie privée (`social_privacy.privacy_officer`)
- Désignation du responsable légal

### Brèches de confidentialité (`social_privacy.privacy_breach`)
- Enregistrement et suivi des incidents
- Modèle de courriel de notification (`data/mail_template_breach.xml`)

### Demandes d'exportation (`social_privacy.data_export_request`)
- Gestion des demandes d'accès aux données personnelles

### Journal d'accès (`social_privacy.privacy_access_log`)
- Traçabilité des accès aux données sensibles

### Règles de rétention (`social_privacy.retention.rule`)
- Règles configurables par modèle Odoo
- Actions : `delete` / `archive` / `anonymize`
- Champ de date configurable (ex. `create_date`, `write_date`)
- Filtre de domaine optionnel pour cibler des enregistrements spécifiques
- Cron d'application automatique

### Versions de politique (`social_privacy.policy_version`)
- Gestion des versions de la politique de confidentialité

### Enregistrements de consentement (`social_privacy.consent_record`)
- Traçabilité des consentements obtenus

### Révisions de conception (`social_privacy.design_review`)
- Évaluations de l'impact sur la vie privée (EFVP)

### Limitations de profil (`social_privacy.profile_limitation`)
- Restrictions sur certains champs/fonctionnalités pour des profils spécifiques

### Anonymisation
- Wizard d'anonymisation complète d'un profil (`social_privacy.anonymize_wizard`)
- Utilisateur anonyme de substitution (`data/anonymous_user.xml`)

### Extension partenaire
- Champs supplémentaires sur `res.partner` pour les droits Loi 25

### Portail
- Page portail de confidentialité (`/my/privacy`)
- Gestion des politiques et consentements par le membre

---

## 23. Adhésions club

**Modules :** `club_membership`, `club_membership_sale`, `club_membership_website`

### Types d'adhésion (`club_membership.membership_type`)
- Nom, durée, prix
- Données initiales de types prédéfinis

### Adhésions (`club_membership.membership`)
- États : `pending` / `active` / `expired` / `cancelled`
- Période (date début, date fin)
- Lien au partenaire
- Cron d'expiration automatique

### Via commande de vente (`club_membership_sale`)
- Produits Odoo configurables comme produit d'adhésion
- Activation automatique à la confirmation de commande
- Activation à la réception du paiement

### Portail web (`club_membership_website`)
- Vitrine publique des types d'adhésion
- Intégration panier `website_sale`
- Page de l'adhésion active dans le portail membre

---

## 24. Events

**Module :** `social_events`

Extension des événements Odoo avec visibilité sociale.

### Champs ajoutés aux événements
- `social_visibility` : `members` (tous les membres) ou par cercle
- `allowed_circle_ids` : cercles ayant accès à l'événement

### Intégration feed
- Les événements avec `social_visibility` apparaissent dans le fil d'actualité
- Visibilité filtrée selon les cercles de l'utilisateur
- Affichage des connexions inscrites à l'événement (max 3 noms)

---

## 25. Website — Blog restreint

**Module :** `website_blog_restricted`

Limite la visibilité d'un blog Odoo à des utilisateurs spécifiques.

### Features
- Ajout d'un champ `visibility` sur `blog.blog` (défaut : `public`)
- Champ `owner_partner_id` pour les blogs avec propriétaire (utilisé pour les règles de visibilité par connexion/relation)
- Intègre le mixin de visibilité de `club_social_profile`
- Niveaux de visibilité disponibles : public / membres / connexions / relations
- Méthode `is_accessible_by(user)` pour vérifier l'accès
- Les articles de blog héritent de la visibilité du blog parent

---

## 26. Website — Membres seulement

**Module :** `website_members_only`

Cache les événements aux visiteurs non connectés.

### Features
- Ajout d'un paramètre `event_login_required` sur `website` (défaut : `True`)
- Configurable dans les paramètres du site web (vue `res_config_settings`)
- Redirection automatique vers la page de connexion pour :
  - La liste des événements
  - La page détail d'un événement
- Les membres connectés ne sont pas affectés

---

## Résumé des dépendances inter-modules

```
social_base
    └── club_social_profile  ← PIVOT
            ├── social_story
            ├── social_gallery
            ├── social_group
            ├── social_messaging  ← dépend aussi social_safety
            ├── social_circles    ← dépend aussi partner_multi_relation
            ├── social_discovery  ← dépend aussi social_circles
            ├── social_safety     ← dépend aussi social_discovery
            ├── social_consent
            ├── social_negotiation
            ├── social_reputation ← dépend aussi social_discovery
            ├── social_onboarding ← dépend aussi club_membership
            ├── social_events     ← dépend aussi social_circles
            ├── social_calling    ← dépend aussi social_safety, social_notifications
            ├── club_social_moderation
            ├── club_social_profile_bdsm
            └── social_notifications  ← agrège tous les modules ci-dessus

social_feed  ← agrège club_social_profile + social_safety + social_circles
              + social_group + social_events + social_base + social_story
              + social_governance + social_gallery

social_age_gate    ← dépend social_onboarding
social_analytics   ← agrège la plupart des modules
social_privacy     ← agrège TOUS les modules sociaux + OCA data_protection

diverse_club_social  ← APPLICATION FEUILLE — installe tous les modules ci-dessus
```
