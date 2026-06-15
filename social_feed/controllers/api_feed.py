import logging

from odoo import http
from odoo.http import request
from odoo.exceptions import AccessError

from odoo.addons.social_base.controllers.mixins import SocialBaseMixin
from odoo.addons.social_feed.models.user_preference import FEED_TYPES, BOOST_MIN, BOOST_MAX

_logger = logging.getLogger(__name__)

_VALID_TYPES = frozenset(t for t, _ in FEED_TYPES)


class SocialFeedAPI(SocialBaseMixin, http.Controller):

    @http.route('/social/api/feed', type='http', auth='user', methods=['GET'], csrf=False)
    def api_feed(self, limit=20, offset=0, types=None, sort='recent', **kwargs):
        """
        GET /social/api/feed?limit=20&offset=0&types=post,story,event,proposal&sort=relevance

        Retourne le fil d'actualité de l'utilisateur authentifié.
        Toutes les règles de visibilité sont respectées.

        Paramètres :
          limit     — max items retournés (défaut 20, max 100)
          offset    — décalage pour la pagination
          types     — filtre par type séparé par virgules (défaut : tous)
          sort      — 'recent' (défaut, chronologique DESC) ou 'relevance'
        """
        if sort not in ('recent', 'relevance'):
            sort = 'recent'
        try:
            self._validate_auth()
            parsed_types = [t.strip() for t in types.split(',')] if types else None
            result = request.env['social_feed.service'].get_feed(
                limit=int(limit),
                offset=int(offset),
                types=parsed_types,
                sort=sort,
            )
            return self._success_response(result)
        except AccessError as e:
            return self._error_response(str(e), 'AUTH_ERROR', 401)
        except Exception:
            _logger.exception('Error building social feed')
            return self._error_response('Internal error', 'FEED_ERROR')

    # ── Read state ───────────────────────────────────────────────────────────

    @http.route('/social/api/feed/mark_read', type='jsonrpc', auth='user',
                methods=['POST'], csrf=False)
    def mark_read(self, item_type=None, item_id=None, **kw):
        try:
            user = self._validate_auth()
        except AccessError:
            return {'success': False, 'error': 'auth'}
        if item_type not in _VALID_TYPES:
            return {'success': False, 'error': 'invalid_type'}
        try:
            iid = int(item_id)
        except (TypeError, ValueError):
            return {'success': False, 'error': 'invalid_id'}
        request.env['social_feed.read_marker'].sudo().mark_read(user.id, item_type, iid)
        return {'success': True}

    @http.route('/social/api/feed/mark_unread', type='jsonrpc', auth='user',
                methods=['POST'], csrf=False)
    def mark_unread(self, item_type=None, item_id=None, **kw):
        try:
            user = self._validate_auth()
        except AccessError:
            return {'success': False, 'error': 'auth'}
        if item_type not in _VALID_TYPES:
            return {'success': False, 'error': 'invalid_type'}
        try:
            iid = int(item_id)
        except (TypeError, ValueError):
            return {'success': False, 'error': 'invalid_id'}
        request.env['social_feed.read_marker'].sudo().mark_unread(user.id, item_type, iid)
        return {'success': True}

    # ── Preferences ──────────────────────────────────────────────────────────

    @http.route('/social/api/feed/preferences', type='jsonrpc', auth='user',
                methods=['POST'], csrf=False)
    def get_preferences(self, **kw):
        """Returns current boosts + the available types + the allowed range.

        type='jsonrpc' forces POST in Odoo, so the read endpoint is also a
        POST with an empty body. The write endpoint sits on a distinct
        URL (/set) to avoid the ambiguity.
        """
        try:
            user = self._validate_auth()
        except AccessError:
            return {'success': False, 'error': 'auth'}
        boosts = request.env['social_feed.user_preference'].sudo().boosts_for_user(user.id)
        return {
            'success': True,
            'data': {
                'boosts': boosts,
                'available_types': [t for t, _ in FEED_TYPES],
                'range': {'min': BOOST_MIN, 'max': BOOST_MAX},
            },
        }

    @http.route('/social/api/feed/preferences/set', type='jsonrpc', auth='user',
                methods=['POST'], csrf=False)
    def set_preference(self, item_type=None, boost_factor=None, **kw):
        try:
            user = self._validate_auth()
        except AccessError:
            return {'success': False, 'error': 'auth'}
        if item_type not in _VALID_TYPES:
            return {'success': False, 'error': 'invalid_type'}
        try:
            boost = float(boost_factor)
        except (TypeError, ValueError):
            return {'success': False, 'error': 'invalid_boost'}
        pref = request.env['social_feed.user_preference'].sudo().set_boost(
            user.id, item_type, boost,
        )
        return {'success': True, 'data': {'boost_factor': pref.boost_factor}}
