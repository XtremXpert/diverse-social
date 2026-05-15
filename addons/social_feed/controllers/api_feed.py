import logging

from odoo import http
from odoo.http import request
from odoo.exceptions import AccessError

from odoo.addons.social_base.controllers.mixins import SocialBaseMixin

_logger = logging.getLogger(__name__)


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
