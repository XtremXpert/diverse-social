import json
import logging
import os

from odoo.http import Controller, request, route
from odoo.tools.misc import file_path

_logger = logging.getLogger(__name__)

ICON_DIRS = {
    'meteo': '/social_pwa/static/src/img',
    'marque': '/social_pwa/static/src/img/marque',
}


def icon_dir(get):
    """Icon folder for `social_pwa.icon_set`: `meteo` (camouflage, default) or `marque`."""
    return ICON_DIRS.get(get('social_pwa.icon_set', 'meteo'), ICON_DIRS['meteo'])


class PwaController(Controller):

    # ── Manifest ────────────────────────────────────────────────────────────
    @route('/manifest.webmanifest', auth='public', type='http', methods=['GET'], csrf=False)
    def manifest(self):
        """Web App Manifest. Camouflaged by default (see ir.config_parameter).

        Public route — the manifest itself doesn't reveal anything more than
        the URL pattern does. Cached aggressively by browsers, so changes
        require either a bump in app_name or a cache flush.
        """
        get = request.env['ir.config_parameter'].sudo().get_str
        icons = icon_dir(get)
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
                    'src': f'{icons}/icon-192.png',
                    'sizes': '192x192',
                    'type': 'image/png',
                    'purpose': 'any',
                },
                {
                    'src': f'{icons}/icon-512.png',
                    'sizes': '512x512',
                    'type': 'image/png',
                    'purpose': 'any',
                },
                {
                    'src': f'{icons}/icon-maskable-512.png',
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

        Delegates to the standard mail.push.device helper, which generates
        the VAPID key pair on first use. Wrapped in a controller because the
        model's ACL is system-only — portal users can't call it over RPC.
        """
        key = request.env['mail.push.device'].sudo().get_web_push_vapid_public_key()
        return request.make_response(key or '', headers=[('Content-Type', 'text/plain')])

    # ── Push subscription endpoint ───────────────────────────────────────────
    @route('/pwa/subscribe', auth='user', type='jsonrpc', methods=['POST'], csrf=False)
    def subscribe(self, endpoint=None, keys=None, **kw):
        """Register a PushSubscription for the current user.

        Payload mirrors the JS PushSubscription.toJSON() shape:
            {endpoint: "...", keys: {p256dh: "...", auth: "..."}}

        Stored in the standard mail.push.device table; delivery is handled
        by the standard mail.push queue + cron.
        """
        if not endpoint or not isinstance(keys, dict):
            return {'success': False, 'error': 'bad_payload'}
        p256dh = keys.get('p256dh')
        auth = keys.get('auth')
        if not (p256dh and auth):
            return {'success': False, 'error': 'missing_keys'}

        partner = request.env.user.partner_id
        vals = {
            'partner_id': partner.id,
            'endpoint': endpoint,
            'keys': json.dumps({'p256dh': p256dh, 'auth': auth}),
        }
        Device = request.env['mail.push.device'].sudo()
        existing = Device.search([('endpoint', '=', endpoint)], limit=1)
        if existing:
            # Re-up the keys + reassign to current user (devices switch owners).
            existing.write(vals)
            return {'success': True, 'id': existing.id, 'updated': True}

        device = Device.create(vals)
        return {'success': True, 'id': device.id, 'updated': False}

    @route('/pwa/unsubscribe', auth='user', type='jsonrpc', methods=['POST'], csrf=False)
    def unsubscribe(self, endpoint=None, **kw):
        if not endpoint:
            return {'success': False, 'error': 'bad_payload'}
        Device = request.env['mail.push.device'].sudo()
        Device.search([
            ('endpoint', '=', endpoint),
            ('partner_id', '=', request.env.user.partner_id.id),
        ]).unlink()
        return {'success': True}
