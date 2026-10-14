# Social Mobile

API de l'application mobile (iOS) du réseau social : inscription par QR code et parrainage en personne.

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

## Authentification

`Authorization: Bearer <clé>` : clé API de portée `social_mobile`, valable 180 jours par défaut (réglable).
Elle n'ouvre que `/api/social/v1` ; une clé `rpc` n'y donne pas accès, et elle n'ouvre pas `/json/2`.

## Points d'entrée (`/api/social/v1`)

Réponses JSON. Erreurs : `{"error": {"code", "message"}}`.

### Publics (nouveau venu)

| Méthode | Chemin | Corps / en-têtes | Réponse |
|---|---|---|---|
| `POST` | `/enroll` | `{"email", "device_name", "consent": true}` | `201 {"enrollment_id", "poll_secret", "qr_secret", "period", "expires_at"}` ; `400` invalide ; `429` trop d'inscriptions en attente |
| `GET` | `/enroll/<id>` | `X-Enrollment-Secret: <poll_secret>` | `{"state": "pending"}`, puis une seule fois `{"state": "active", "key", "expires_at", "user_id"}` ; `404` inconnue, échue ou déjà remise |
| `DELETE` | `/enroll/<id>` | `X-Enrollment-Secret` | Annule une inscription en attente |
| `POST` | `/enroll/review` | `{"code"}` | Examen App Store : clé du compte de démonstration si le code réglé dans Odoo correspond ; `404` sinon |

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

## Examen App Store

L'application n'affichant qu'un QR code avant parrainage, l'examinateur d'Apple ne pourrait pas y entrer. Dans
Paramètres → Application mobile, choisir un **compte de démonstration** (données de démonstration seulement) et un
**code d'examen** ; l'application accepte ce code à la place du parrainage. Vider le code une fois l'application
approuvée.
