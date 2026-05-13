import logging

from odoo import http
from odoo.http import request
from odoo.exceptions import AccessError

from odoo.addons.social_base.controllers.mixins import SocialBaseMixin

_logger = logging.getLogger(__name__)


class SocialSearchAPI(SocialBaseMixin, http.Controller):

    @http.route('/social/api/search', type='http', auth='user', methods=['GET'], csrf=False)
    def api_search(self, q='', types=None, limit=10, offset=0, **kwargs):
        """
        GET /social/api/search?q=texte&types=profile,group&limit=10&offset=0

        Paramètres :
          q       — terme de recherche (vide = tout retourner)
          types   — liste séparée par virgules parmi : profile, group, event, post
                    (défaut : tous)
          limit   — max résultats par type (défaut 10, max 50)
          offset  — décalage par type
        """
        try:
            self._validate_auth()
            parsed_types = [t.strip() for t in types.split(',')] if types else None
            results = request.env['social_search.service'].search_all(
                query=q,
                limit=int(limit),
                offset=int(offset),
                types=parsed_types,
            )
            total = sum(len(v) for v in results.values())
            return self._success_response({'query': q, 'total': total, 'results': results})

        except AccessError as e:
            return self._error_response(str(e), 'AUTH_ERROR', 401)
        except Exception:
            _logger.exception('Error during social search')
            return self._error_response('Internal error', 'SEARCH_ERROR')
