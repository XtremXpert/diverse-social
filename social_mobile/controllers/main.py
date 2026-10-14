"""API de l'application mobile (contrat : README.md du module).

Deux familles de routes sous /api/social/v1 :

* publiques, pour le nouveau venu qui n'a pas encore de compte : ``/enroll`` ;
* authentifiées par « Authorization: Bearer <clé> », clé API de portée « social_mobile ».
  Une clé « rpc » n'y donne pas accès, et une clé « social_mobile » n'ouvre pas /json/2.
"""
import datetime
import hmac
import json

from odoo import http
from odoo.exceptions import UserError, ValidationError
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

    @http.route(f'{API}/token/renew', methods=['POST'], **ROUTE)
    def renew_token(self):
        body = json_body() or {}
        name = (body.get('device_name') or 'Application mobile')[:64]
        Keys = request.env['res.users.apikeys']
        key, expiration = Keys._social_mobile_generate(name)
        header = request.httprequest.headers.get('Authorization', '')
        Keys._social_mobile_retire(header.split(' ', 1)[-1].strip())
        return json_response({'key': key, 'expires_at': iso(expiration)})
