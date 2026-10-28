"""API de l'application mobile (contrat : README.md du module).

Deux familles de routes sous /api/social/v1 :

* publiques, pour le nouveau venu qui n'a pas encore de compte : ``/enroll`` ;
* authentifiées par « Authorization: Bearer <clé> », clé API de portée « social_mobile ».
  Une clé « rpc » n'y donne pas accès, et une clé « social_mobile » n'ouvre pas /json/2.
"""
import base64
import binascii
import datetime
import hmac
import json

from odoo import http
from odoo.exceptions import AccessDenied, UserError, ValidationError
from odoo.http import request

from ..models.enrollment import PERIOD

API = '/api/social/v1'
ROUTE = {'auth': 'bearer', 'bearer_scope': 'social_mobile', 'type': 'http', 'csrf': False, 'readonly': False}
PUBLIC = {'auth': 'public', 'type': 'http', 'csrf': False, 'readonly': False, 'sitemap': False}


def json_response(payload, status=200):
    return request.make_response(
        json.dumps(payload, ensure_ascii=False),
        headers=[('Content-Type', 'application/json; charset=utf-8'), ('Cache-Control', 'no-store')],
        status=status,
    )


def error(status, code, message):
    return json_response({'error': {'code': code, 'message': message}}, status=status)


def json_body():
    try:
        body = request.httprequest.get_json(force=True, silent=False)
    except Exception:  # noqa: BLE001 - corps illisible : 400 plutôt qu'une trace serveur
        return None
    return body if isinstance(body, dict) else None


def iso(value):
    return value.replace(tzinfo=datetime.UTC).isoformat() if value else None


class SocialMobileApi(http.Controller):

    # ── Inscription (publique) ───────────────────────────────────────────────

    @http.route(f'{API}/enroll', methods=['POST'], **PUBLIC)
    def enroll_start(self):
        body = json_body()
        if body is None:
            return error(400, 'invalid_json', "Corps JSON attendu.")
        try:
            enrollment, poll_secret = request.env['social_mobile.enrollment']._api_start(
                body.get('email'), body.get('device_name'), body.get('consent') is True,
                client=request.httprequest.remote_addr)
        except ValidationError as e:
            return error(400, 'invalid', str(e))
        except UserError as e:
            return error(429, 'refused', str(e))
        return json_response({
            'enrollment_id': enrollment.uuid,
            'poll_secret': poll_secret,
            'qr_secret': enrollment.qr_secret,
            'period': PERIOD,
            'expires_at': iso(enrollment.expires_at),
        }, status=201)

    @http.route(f'{API}/policy', methods=['GET'], **PUBLIC)
    def policy(self):
        """Politique de confidentialité en vigueur, affichée avant le consentement."""
        policy = request.env['social_mobile.enrollment']._current_policy()
        if not policy:
            return error(404, 'no_policy', "Aucune politique de confidentialité en vigueur.")
        return json_response({'version': policy.version_number, 'name': policy.name, 'content_html': str(policy.content or '')})

    @http.route(f'{API}/enroll/<string:enrollment_id>', methods=['GET'], **PUBLIC)
    def enroll_status(self, enrollment_id):
        secret = request.httprequest.headers.get('X-Enrollment-Secret', '')
        enrollment = request.env['social_mobile.enrollment']._api_find(enrollment_id, secret)
        if not enrollment:
            return error(404, 'not_found', "Inscription inconnue ou échue.")
        state, payload = enrollment._api_collect()
        if state == 'gone':
            return error(404, 'not_found', "Inscription inconnue ou échue.")
        return json_response(dict(payload or {}, state=state))

    @http.route(f'{API}/enroll/<string:enrollment_id>', methods=['DELETE'], **PUBLIC)
    def enroll_cancel(self, enrollment_id):
        secret = request.httprequest.headers.get('X-Enrollment-Secret', '')
        enrollment = request.env['social_mobile.enrollment']._api_find(enrollment_id, secret)
        if enrollment and enrollment.state == 'pending':
            enrollment.unlink()
        return json_response({'deleted': True})

    @http.route(f'{API}/enroll/review', methods=['POST'], **PUBLIC)
    def enroll_review(self):
        """Accès de l'examen App Store : un code réglé dans Odoo ouvre le compte de démonstration."""
        body = json_body() or {}
        ICP = request.env['ir.config_parameter'].sudo()
        expected = ICP.get_str('social_mobile.review_code') or ''
        user = request.env['res.users'].sudo().browse(ICP.get_int('social_mobile.review_user_id')).exists()
        code = str(body.get('code') or '')
        if not expected or not user or not user.active or not hmac.compare_digest(expected, code):
            return error(404, 'not_found', "Code inconnu.")
        key, expiration = request.env['res.users.apikeys'].with_user(user)._social_mobile_generate('Examen App Store')
        return json_response({'state': 'active', 'key': key, 'expires_at': iso(expiration), 'user_id': user.id})

    # ── Compte existant (publique) ───────────────────────────────────────────

    def _login_success(self, user, body):
        """Fin commune des connexions : compte admissible, consentement, clé."""
        refusal = user._social_mobile_login_refusal()
        if refusal:
            return error(403, 'refused', refusal)
        Consent = request.env['social_privacy.consent'].sudo()
        if not Consent.has_valid_consent(user):
            Consent.record_consent(user, request.env['social_mobile.enrollment']._current_policy(), source='api')
        name = (body.get('device_name') or 'Application mobile')[:64]
        key, expiration = request.env['res.users.apikeys'].with_user(user)._social_mobile_generate(name)
        return json_response({'state': 'active', 'key': key, 'expires_at': iso(expiration), 'user_id': user.id})

    def _login_body(self):
        """Corps d'une étape de connexion : JSON, avec le consentement à la politique en vigueur
        (l'application l'affiche avant le courriel, comme à l'inscription)."""
        body = json_body()
        if body is None:
            return None, error(400, 'invalid_json', "Corps JSON attendu.")
        if not request.env['social_mobile.enrollment']._current_policy():
            return None, error(503, 'no_policy', "Aucune politique de confidentialité en vigueur.")
        if body.get('consent') is not True:
            return None, error(400, 'consent_required', "Le consentement à la politique de confidentialité est requis.")
        return body, None

    def _login_challenge(self, login, secret):
        return json_response({
            'state': 'code_required',
            'step': login.step,
            'login_id': login.uuid,
            'login_secret': secret,
            'expires_at': iso(login.expires_at),
        }, status=202)

    @http.route(f'{API}/login/code', methods=['POST'], **PUBLIC)
    def login_code(self):
        """Envoie un code au courriel d'un compte existant. Même réponse que le compte existe ou non."""
        body, err = self._login_body()
        if err:
            return err
        try:
            login, secret = request.env['social_mobile.login']._api_request_code(
                body.get('email'), body.get('device_name'), client=request.httprequest.remote_addr)
        except ValidationError as e:
            return error(400, 'invalid', str(e))
        except UserError as e:
            return error(429, 'refused', str(e))
        return self._login_challenge(login, secret)

    @http.route(f'{API}/login/password', methods=['POST'], **PUBLIC)
    def login_password(self):
        body, err = self._login_body()
        if err:
            return err
        try:
            user, login, secret = request.env['social_mobile.login']._api_password(
                body.get('email'), body.get('password'), body.get('device_name'),
                client=request.httprequest.remote_addr)
        except AccessDenied:
            return error(401, 'invalid_credentials', "Courriel ou mot de passe incorrect.")
        except UserError as e:
            return error(409, 'refused', str(e))
        if login:
            return self._login_challenge(login, secret)
        return self._login_success(user, body)

    @http.route(f'{API}/login/<string:login_id>', methods=['POST'], **PUBLIC)
    def login_verify(self, login_id):
        body, err = self._login_body()
        if err:
            return err
        secret = request.httprequest.headers.get('X-Login-Secret', '')
        login = request.env['social_mobile.login']._api_find(login_id, secret)
        if not login:
            return error(404, 'not_found', "Code échu : recommencez la connexion.")
        result = login._api_verify(str(body.get('code') or ''))
        if result is None:
            return error(401, 'invalid_code', "Code incorrect.")
        if result == 'totp':
            return json_response({'state': 'code_required', 'step': 'totp', 'login_id': login.uuid,
                                  'expires_at': iso(login.expires_at)}, status=202)
        return self._login_success(result, body)

    # ── Parrainage ───────────────────────────────────────────────────────────

    def _scanned(self, body):
        if body is None:
            return None, error(400, 'invalid_json', "Corps JSON attendu.")
        enrollment = request.env['social_mobile.enrollment']._api_scanned(body.get('enrollment_id'), body.get('code'))
        if not enrollment:
            return None, error(404, 'invalid_code', "QR code échu ou inconnu : demandez à la personne de le réafficher.")
        return enrollment, None

    @http.route(f'{API}/sponsor/preview', methods=['POST'], **ROUTE)
    def sponsor_preview(self):
        """Ce que le parrain confirme : le courriel saisi par la personne qu'il a devant lui."""
        enrollment, err = self._scanned(json_body())
        if err:
            return err
        refusal = request.env.user._social_mobile_sponsor_refusal()
        return json_response({
            'enrollment_id': enrollment.uuid,
            'email': enrollment.email,
            'device_name': enrollment.device_name or None,
            'state': enrollment.state,
            'can_sponsor': not refusal,
            'refusal': refusal,
        })

    @http.route(f'{API}/sponsor/confirm', methods=['POST'], **ROUTE)
    def sponsor_confirm(self):
        body = json_body()
        enrollment, err = self._scanned(body)
        if err:
            return err
        try:
            newcomer = enrollment._api_sponsor(request.env.user, statement=(body.get('statement') or '').strip() or None)
        except (UserError, ValidationError) as e:
            return error(409, 'refused', str(e))
        Profile = request.env['club_social_profile.profile'].sudo()
        return json_response({'newcomer': {'id': newcomer.id, 'name': Profile._display_name_for_user(newcomer)}})

    # ── Compte ───────────────────────────────────────────────────────────────

    @http.route(f'{API}/me', methods=['GET'], **ROUTE)
    def me(self):
        user = request.env.user
        request.env['social_mobile.enrollment']._api_acknowledge(user)
        Profile = request.env['club_social_profile.profile'].sudo()
        profile = Profile.search([('user_id', '=', user.id)], limit=1)
        refusal = user._social_mobile_sponsor_refusal()
        return json_response({
            'api_version': 1,
            'server_time': iso(datetime.datetime.now()),
            'user': {
                'id': user.id,
                'name': Profile._display_name_for_user(user),
                'email': user.email or None,
            },
            'is_member': user.has_group('social_base.group_social_user'),
            'onboarding_done': bool(profile.onboarding_done),
            'can_sponsor': not refusal,
            'install_url': request.env['ir.config_parameter'].sudo().get_str('social_mobile.install_url') or None,
        })

    @http.route(f'{API}/me', methods=['DELETE'], **ROUTE)
    def delete_account(self):
        """Suppression du compte depuis l'application (exigée par l'App Store)."""
        user = request.env.user
        if not user.share:
            return error(409, 'internal_user', "Un compte interne se supprime depuis Odoo.")
        request.env['res.users.apikeys']._social_mobile_revoke_all()
        user._deactivate_portal_user()
        return json_response({'deleted': True})

    # ── Profil (accueil dans l'application) ──────────────────────────────────

    def _profile(self):
        return request.env['club_social_profile.profile'].sudo().get_or_create_for_user(request.env.user)

    @http.route(f'{API}/profile', methods=['GET'], **ROUTE)
    def profile(self):
        return json_response(self._profile()._mobile_payload())

    @http.route(f'{API}/profile', methods=['POST'], **ROUTE)
    def update_profile(self):
        """Modifie les champs reçus ; les autres restent tels quels."""
        body = json_body()
        if body is None:
            return error(400, 'invalid_json', "Corps JSON attendu.")
        profile = self._profile()
        try:
            profile._mobile_update(body)
        except (UserError, ValidationError) as e:
            return error(422, 'invalid', str(e))
        return json_response(profile._mobile_payload())

    @http.route(f'{API}/profile/photo', methods=['POST'], **ROUTE)
    def update_photo(self):
        """Photo de profil : ``{"data": "<jpeg ou png en base64>"}``."""
        body = json_body()
        if body is None or not isinstance(body.get('data'), str):
            return error(400, 'invalid_json', "Corps JSON attendu : {\"data\": base64}.")
        try:
            data = base64.b64decode(body['data'], validate=True)
        except (binascii.Error, ValueError):
            return error(400, 'invalid', "Image illisible (base64 attendu).")
        if not data or len(data) > 10 * 1024 * 1024:
            return error(400, 'invalid', "Image vide ou trop lourde (10 Mo au plus).")
        profile = self._profile()
        try:
            profile._mobile_set_photo(data)
        except (UserError, ValidationError) as e:
            return error(422, 'invalid', str(e))
        return json_response({'has_photo': bool(profile.profile_image)})

    @http.route(f'{API}/profile/complete', methods=['POST'], **ROUTE)
    def complete_profile(self):
        """Fin de l'accueil : le membre apparaît dans la grille. Exige l'année de naissance."""
        profile = self._profile()
        try:
            profile._mobile_complete()
        except (UserError, ValidationError) as e:
            return error(422, 'birth_year_required', str(e))
        return json_response({'onboarding_done': True})

    @http.route(f'{API}/token/renew', methods=['POST'], **ROUTE)
    def renew_token(self):
        body = json_body() or {}
        name = (body.get('device_name') or 'Application mobile')[:64]
        Keys = request.env['res.users.apikeys']
        key, expiration = Keys._social_mobile_generate(name)
        header = request.httprequest.headers.get('Authorization', '')
        Keys._social_mobile_retire(header.split(' ', 1)[-1].strip())
        return json_response({'key': key, 'expires_at': iso(expiration)})


# Niveau d'intérêt FetLife -> kink_level : Into=oui, Curious=curieux, Soft limit=soft.
_FETLIFE_LEVELS = {'into': 'oui', 'curious': 'curieux', 'curious about': 'curieux',
                  'soft limit': 'soft', 'expert': 'expert'}


class SocialMobileImport(http.Controller):
    """Import ponctuel des données propres du membre (pont FetLife via extension ou WebView).

    Session web classique (auth='user') : l'usager est connecté sur le site dans son navigateur.
    """

    @http.route(f'{API}/import/fetlife', auth='user', type='http', methods=['POST'], csrf=False)
    def import_fetlife(self):
        body = json_body()
        if body is None or not isinstance(body.get('kinks', []), list):
            return error(400, 'invalid', 'Corps attendu : {"kinks": [{"name", "level"}], "fetlife_url"}.')
        Profile = request.env['club_social_profile.profile'].sudo()
        profile = Profile.get_or_create_for_user(request.env.user)
        Kink = request.env['club_social_profile_bdsm.kink'].sudo()
        Level = request.env['club_social_profile_bdsm.kink_level'].sudo()
        url = (body.get('fetlife_url') or '').strip()
        if url.startswith('https://fetlife.com/') and not profile.fetlife_url:
            profile.fetlife_url = url
        matched, skipped, unmatched = [], 0, []
        for item in body['kinks'][:200]:
            name = str(item.get('name') or '').strip()
            if not name:
                continue
            # Match in the member's language first, then EN and FR (names are translatable).
            kink = Kink.search([('name', 'ilike', name)], limit=1)
            for lang in ('en_US', 'fr_FR'):
                if kink:
                    break
                kink = Kink.with_context(lang=lang).search([('name', 'ilike', name)], limit=1)
            if not kink:
                unmatched.append(name)
                continue
            if kink in profile.kink_level_ids.kink_id:
                skipped += 1
                continue
            Level.create({
                'profile_id': profile.id,
                'kink_id': kink.id,
                'level': _FETLIFE_LEVELS.get(str(item.get('level', '')).lower(), 'curieux'),
            })
            matched.append(name)
        return json_response({'matched': matched, 'skipped': skipped, 'unmatched': unmatched})
