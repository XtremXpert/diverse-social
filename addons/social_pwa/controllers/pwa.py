import json
import logging
import os

from odoo.http import Controller, request, route
from odoo.tools.misc import file_path

_logger = logging.getLogger(__name__)


class PwaController(Controller):

    # ── Manifest ────────────────────────────────────────────────────────────
    @route('/manifest.webmanifest', auth='public', type='http', methods=['GET'], csrf=False)
    def manifest(self):
        """Web App Manifest. Camouflaged by default (see ir.config_parameter).

        Public route — the manifest itself doesn't reveal anything more than
        the URL pattern does. Cached aggressively by browsers, so changes
        require either a bump in app_name or a cache flush.
        """
        get = request.env['ir.config_parameter'].sudo().get_param
        payload = {
            'name': get('social_pwa.app_name', 'MétéoMédia'),
            'short_name': get('social_pwa.app_short_name', 'Météo'),
            'description': get('social_pwa.app_description', ''),
            'start_url': get('social_pwa.start_url', '/my/dashboard'),
            'scope': '/',
            'display': 'standalone',
            'orientation': 'portrait-primary',
            'theme_color': get('social_pwa.theme_color', '#5fa8d3'),
            'background_color': get('social_pwa.background_color', '#ffffff'),
            'icons': [
                {
                    'src': '/social_pwa/static/src/img/icon-192.png',
                    'sizes': '192x192',
                    'type': 'image/png',
                    'purpose': 'any',
                },
                {
                    'src': '/social_pwa/static/src/img/icon-512.png',
                    'sizes': '512x512',
                    'type': 'image/png',
                    'purpose': 'any',
                },
                {
                    'src': '/social_pwa/static/src/img/icon-maskable-512.png',
                    'sizes': '512x512',
                    'type': 'image/png',
                    'purpose': 'maskable',
                },
            ],
        }
        return request.make_response(
            json.dumps(payload, ensure_ascii=False),
            headers=[
                ('Content-Type', 'application/manifest+json'),
                ('Cache-Control', 'public, max-age=3600'),
            ],
        )

    # ── Service worker ───────────────────────────────────────────────────────
    @route('/sw.js', auth='public', type='http', methods=['GET'], csrf=False)
    def service_worker(self):
        """Serve the service worker file from the site root.

        Browsers scope a SW to the directory of the URL that registered it,
        so to control the whole origin we *must* serve it from `/`. The
        Service-Worker-Allowed header could relax that, but root-serving is
        simpler and supported everywhere.
        """
        try:
            path = file_path('social_pwa/static/src/js/service-worker.js')
        except FileNotFoundError:
            return request.not_found()
        with open(path, 'rb') as f:
            content = f.read()
        return request.make_response(
            content,
            headers=[
                ('Content-Type', 'application/javascript'),
                # Discourage stale SW: browsers re-fetch the SW script on
                # every navigation when its max-age is small.
                ('Cache-Control', 'max-age=0, no-cache, no-store, must-revalidate'),
                ('Service-Worker-Allowed', '/'),
            ],
        )

    # ── Offline shell ────────────────────────────────────────────────────────
    @route('/pwa/offline', auth='public', website=True, sitemap=False)
    def offline(self):
        """Fallback page rendered by the service worker on network failure.

        Kept deliberately bland — no member content, no branding the user
        wouldn't want a passing eye to see.
        """
        return request.render('social_pwa.offline_page')

    # ── VAPID public key ─────────────────────────────────────────────────────
    @route('/pwa/vapid_public_key', auth='user', type='http', methods=['GET'], csrf=False)
    def vapid_public_key(self):
        """Front-end fetches this once before subscribing.

        Returns empty string if push isn't configured yet — the client side
        treats that as "push disabled" and silently skips the prompt.
        """
        key = request.env['ir.config_parameter'].sudo().get_param(
            'social_pwa.vapid_public_key', '',
        )
        return request.make_response(key, headers=[('Content-Type', 'text/plain')])

    # ── Push subscription endpoint ───────────────────────────────────────────
    @route('/pwa/subscribe', auth='user', type='json', methods=['POST'], csrf=False)
    def subscribe(self, endpoint=None, keys=None, **kw):
        """Register a PushSubscription for the current user.

        Payload mirrors the JS PushSubscription.toJSON() shape:
            {endpoint: "...", keys: {p256dh: "...", auth: "..."}}
        """
        if not endpoint or not isinstance(keys, dict):
            return {'success': False, 'error': 'bad_payload'}
        p256dh = keys.get('p256dh')
        auth = keys.get('auth')
        if not (p256dh and auth):
            return {'success': False, 'error': 'missing_keys'}

        user = request.env.user
        ua = (request.httprequest.headers.get('User-Agent') or '')[:200]

        Sub = request.env['social_pwa.subscription'].sudo()
        existing = Sub.search([('endpoint', '=', endpoint)], limit=1)
        if existing:
            # Re-up the keys + reassign to current user (devices switch owners).
            existing.write({
                'user_id': user.id, 'p256dh': p256dh, 'auth': auth,
                'user_agent': ua,
            })
            return {'success': True, 'id': existing.id, 'updated': True}

        sub = Sub.create({
            'user_id': user.id, 'endpoint': endpoint,
            'p256dh': p256dh, 'auth': auth, 'user_agent': ua,
        })
        return {'success': True, 'id': sub.id, 'updated': False}

    @route('/pwa/unsubscribe', auth='user', type='json', methods=['POST'], csrf=False)
    def unsubscribe(self, endpoint=None, **kw):
        if not endpoint:
            return {'success': False, 'error': 'bad_payload'}
        Sub = request.env['social_pwa.subscription'].sudo()
        Sub.search([('endpoint', '=', endpoint),
                    ('user_id', '=', request.env.user.id)]).unlink()
        return {'success': True}
