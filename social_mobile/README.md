# Social Mobile

API de l'application mobile (iOS) du réseau social : inscription par QR code et parrainage en personne, ou
connexion d'un compte existant.

## Parcours d'inscription

1. Le membre affiche dans son application le **QR code d'installation** (lien App Store non listé, réglé dans
   Paramètres → Application mobile). Le nouveau venu le scanne avec l'appareil photo et installe l'application.
2. Au premier lancement, le nouveau venu saisit son **courriel** et donne son consentement (Loi 25), puis
   l'application n'affiche **qu'un QR code**, renouvelé toutes les 30 secondes.
3. Un membre scanne ce QR code dans son application, voit le courriel saisi et confirme le parrainage. Odoo :
   - crée le compte (utilisateur portail, connexion = courriel) et son profil ;
   - crée le parrainage (`social_reputation.vouching`, actif) au nom du parrain : la **chaîne de confiance** s'applique ;
   - crée et active l'adhésion réglée dans les paramètres (par défaut « Membre régulier ») : l'accès au réseau
     est **immédiat**, accordé par `club_membership._sync_social_access()` ;
   - connecte le parrain et le nouveau membre (connexion acceptée dans les deux sens), pour qu'ils puissent
     s'écrire dès le départ ;
   - enregistre le consentement (`social_privacy`, source « API / Mobile ») s'il existe une politique en vigueur.
4. L'application du nouveau venu, qui interroge Odoo, reçoit **une seule fois** sa clé API. L'inscription,
   et donc le courriel qu'elle portait, est alors effacée.

Une inscription non parrainée est effacée après 24 heures. Odoo ne dit jamais au nouveau venu si son courriel a
déjà un compte (ce serait révéler qui est membre) : le parrain l'apprend en confirmant.

**Qui peut parrainer :** un membre du réseau (`group_social_user`) avec une adhésion active, au moins un parrain
actif et un profil non banni. Les administrateurs en sont exemptés pour amorcer la chaîne.

## Compte existant

Un membre qui a déjà un compte choisit « J'ai déjà un compte », accepte la politique en vigueur, saisit son
courriel, puis au choix :

- **code par courriel** : 6 chiffres, valables 10 minutes, 5 essais ;
- **mot de passe** du site (connexion Odoo, avec son délai après échecs ; une clé API n'est pas acceptée).

Si la **double authentification** (application d'authentification) est activée sur le compte, son code est
demandé ensuite, **dans les deux cas** : le courriel seul ne la contourne pas. Si elle est exigée par courriel
(`auth_totp_mail`), le code de l'application en tient lieu.

Le compte doit avoir un **parrain actif** enregistré (administrateurs exemptés) et ne pas être banni ; sinon
l'application affiche « Contactez un administrateur du club ». Odoo ne dit jamais si un courriel a un compte :
la demande de code reçoit la même réponse dans tous les cas, le courriel ne part qu'au titulaire d'un compte (le
code, ou la raison du refus), et un mauvais mot de passe répond comme une adresse inconnue. Le consentement à la
politique en vigueur est enregistré s'il manquait.

## Authentification

`Authorization: Bearer <clé>` : clé API de portée `social_mobile`, valable 180 jours par défaut (réglable).
Elle n'ouvre que `/api/social/v1` ; une clé `rpc` n'y donne pas accès, et elle n'ouvre pas `/json/2`.

## Points d'entrée (`/api/social/v1`)

Réponses JSON. Erreurs : `{"error": {"code", "message"}}`.

### Publics (nouveau venu, compte existant)

| Méthode | Chemin | Corps / en-têtes | Réponse |
|---|---|---|---|
| `POST` | `/enroll` | `{"email", "device_name", "consent": true}` | `201 {"enrollment_id", "poll_secret", "qr_secret", "period", "expires_at"}` ; `400` invalide ; `429` trop d'inscriptions en attente |
| `GET` | `/enroll/<id>` | `X-Enrollment-Secret: <poll_secret>` | `{"state": "pending"}`, puis une seule fois `{"state": "active", "key", "expires_at", "user_id"}` ; `404` inconnue, échue ou déjà remise |
| `DELETE` | `/enroll/<id>` | `X-Enrollment-Secret` | Annule une inscription en attente |
| `POST` | `/enroll/review` | `{"code"}` | Examen App Store : clé du compte de démonstration si le code réglé dans Odoo correspond ; `404` sinon |

| `POST` | `/login/code` | `{"email", "device_name", "consent": true}` | `202 {"state": "code_required", "step": "email", "login_id", "login_secret", "expires_at"}`, que le courriel ait un compte ou non ; `429` trop de connexions en cours |
| `POST` | `/login/password` | `{"email", "password", "device_name", "consent": true}` | `200 {"state": "active", "key", "expires_at", "user_id"}` ; `202` comme ci-dessus si un code est exigé (`step` : `totp` ou `email`) ; `401` courriel ou mot de passe incorrect ; `403` compte refusé (raison dans `message`) |
| `POST` | `/login/<login_id>` | `X-Login-Secret`, `{"code", "device_name", "consent": true}` | `200` clé comme ci-dessus ; `202 {"step": "totp"}` si la double authentification est exigée après le code courriel (même `login_id`) ; `401` code incorrect ; `403` compte refusé ; `404` échu ou essais épuisés |

**QR code du nouveau venu :** JSON `{"v": 1, "k": "enroll", "id": <enrollment_id>, "c": <code>}`, où
`code = HMAC-SHA256(qr_secret, str(floor(unix_time / period)))` en hexadécimal, tronqué à 10 caractères.
Un code reste accepté pendant environ deux minutes (période en cours et trois précédentes).

### Authentifiés

| Méthode | Chemin | Corps | Réponse |
|---|---|---|---|
| `GET` | `/me` | | `{"user": {"id", "name", "email"}, "is_member", "onboarding_done", "can_sponsor", "install_url", …}`. `name` est le pseudonyme s'il existe |
| `DELETE` | `/me` | | Supprime le compte (utilisateur portail) et ses clés mobiles |
| `POST` | `/sponsor/preview` | `{"enrollment_id", "code"}` | `{"email", "device_name", "can_sponsor", "refusal"}` ; `404` QR code échu |
| `POST` | `/sponsor/confirm` | `{"enrollment_id", "code", "statement"?}` | `{"newcomer": {"id", "name"}}` ; `409` refus (parrain non admissible, courriel déjà inscrit, déjà parrainé par un autre). Idempotent pour le même parrain |
| `POST` | `/token/renew` | `{"device_name"}` | Nouvelle clé ; l'ancienne reste valable 24 heures |
| `GET` | `/profile` | | `{"profile": {…}, "options": {…}, "onboarding_done", "adult_age"}` (voir ci-dessous) |
| `POST` | `/profile` | champs à modifier | Même réponse que `GET` ; `422` valeur refusée (année de naissance de moins de 18 ans, choix inconnu…) |
| `POST` | `/profile/photo` | `{"data": "<jpeg ou png en base64>"}` | `{"has_photo": true}` ; `400` base64 illisible ou plus de 10 Mo ; `422` pas une image |
| `POST` | `/profile/complete` | | `{"onboarding_done": true}` ; `422 birth_year_required` sans année de naissance d'adulte |

## Accueil dans l'application

Un compte créé par parrainage a un profil vide, marqué « non terminé » (`onboarding_done` faux) : la grille
À proximité ne le montre pas. L'application l'impose donc dès que `/me` le dit, avant les onglets, avec les trois
étapes de `/onboarding` sur le site : **photo** (facultative), **à propos de moi** (pronoms, présentation, année
de naissance, ville, région, genre, orientation, citation), **préférences** (visibilité, disponibilité,
recherche, langues, résumé par courriel). Seule l'**année de naissance** est obligatoire (18 ans ou plus) ;
`/profile/complete` la vérifie et marque le profil terminé, qui ne s'écrit jamais par `/profile`.

`profile` : `pronouns`, `bio`, `birth_year`, `city`, `region`, `quote`, `gender`, `orientation`,
`availability`, `visibility` (valeur ou `null`), `digest_email_enabled`, `looking_for_ids`, `language_ids`,
`has_photo`. `options` : pour `gender`, `orientation`, `availability`, `visibility`, une liste
`{"value", "label"}` ; pour `looking_for_ids` et `language_ids`, une liste `{"id", "name"}`. Les libellés sont
dans la langue du membre. `POST /profile` n'écrit que les champs reçus.

## Examen App Store

L'application n'affichant qu'un QR code avant parrainage, l'examinateur d'Apple ne pourrait pas y entrer. Dans
Paramètres → Application mobile, choisir un **compte de démonstration** (données de démonstration seulement) et un
**code d'examen** ; l'application accepte ce code à la place du parrainage. Vider le code une fois l'application
approuvée.
