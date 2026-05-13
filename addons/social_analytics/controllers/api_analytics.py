import logging

from odoo import http
from odoo.http import request
from odoo.exceptions import AccessError

from odoo.addons.social_base.controllers.mixins import SocialBaseMixin

_logger = logging.getLogger(__name__)


class SocialAnalyticsAPI(SocialBaseMixin, http.Controller):

    @http.route('/social/api/analytics/dashboard', type='http', auth='user',
                methods=['GET'], csrf=False)
    def api_dashboard(self, **kwargs):
        """
        GET /social/api/analytics/dashboard

        Retourne toutes les métriques du tableau de bord.
        Accès réservé aux modérateurs et admins.
        """
        try:
            user = self._validate_auth()
            if not user.has_group('social_base.group_social_moderator'):
                return self._error_response('Accès réservé aux modérateurs.', 'FORBIDDEN', 403)
            data = request.env['social_analytics.dashboard'].get_dashboard_data()
            return self._success_response(data)
        except AccessError as e:
            return self._error_response(str(e), 'AUTH_ERROR', 401)
        except Exception:
            _logger.exception('Error computing analytics dashboard')
            return self._error_response('Internal error', 'ANALYTICS_ERROR')

    @http.route('/social/api/analytics/members', type='http', auth='user',
                methods=['GET'], csrf=False)
    def api_members(self, **kwargs):
        """Métriques d'adhésion uniquement."""
        try:
            user = self._validate_auth()
            if not user.has_group('social_base.group_social_moderator'):
                return self._error_response('Accès réservé aux modérateurs.', 'FORBIDDEN', 403)
            from datetime import timedelta
            from odoo import fields
            now = fields.Datetime.now()
            today = fields.Date.today()
            data = request.env['social_analytics.dashboard']._member_stats(
                today,
                now - timedelta(days=30),
                today + timedelta(days=30),
            )
            return self._success_response(data)
        except AccessError as e:
            return self._error_response(str(e), 'AUTH_ERROR', 401)
        except Exception:
            _logger.exception('Error computing member analytics')
            return self._error_response('Internal error', 'ANALYTICS_ERROR')

    @http.route('/social/api/analytics/engagement', type='http', auth='user',
                methods=['GET'], csrf=False)
    def api_engagement(self, **kwargs):
        """Métriques d'engagement uniquement."""
        try:
            user = self._validate_auth()
            if not user.has_group('social_base.group_social_moderator'):
                return self._error_response('Accès réservé aux modérateurs.', 'FORBIDDEN', 403)
            from datetime import timedelta
            from odoo import fields
            data = request.env['social_analytics.dashboard']._engagement_stats(
                fields.Datetime.now() - timedelta(days=30)
            )
            return self._success_response(data)
        except AccessError as e:
            return self._error_response(str(e), 'AUTH_ERROR', 401)
        except Exception:
            _logger.exception('Error computing engagement analytics')
            return self._error_response('Internal error', 'ANALYTICS_ERROR')
