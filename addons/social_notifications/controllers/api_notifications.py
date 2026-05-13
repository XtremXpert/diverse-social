import logging

from odoo import http
from odoo.http import request
from odoo.exceptions import AccessError

from odoo.addons.social_base.controllers.mixins import SocialBaseMixin

_logger = logging.getLogger(__name__)


class SocialNotificationsAPI(SocialBaseMixin, http.Controller):

    @http.route('/social/api/notifications', type='http', auth='user', methods=['GET'], csrf=False)
    def api_list(self, limit=50, offset=0, unread_only='false', **kwargs):
        try:
            user = self._validate_auth()
            domain = [('user_id', '=', user.id)]
            if unread_only.lower() == 'true':
                domain.append(('is_read', '=', False))
            notifs = request.env['club_social_profile.notification'].sudo().search(
                domain,
                order='create_date desc',
                limit=int(limit),
                offset=int(offset),
            )
            unread_count = request.env['club_social_profile.notification'].sudo().search_count(
                [('user_id', '=', user.id), ('is_read', '=', False)]
            )
            return self._success_response({
                'notifications': [self._notif_to_dict(n) for n in notifs],
                'unread_count': unread_count,
            })
        except AccessError as e:
            return self._error_response(str(e), 'AUTH_ERROR', 401)
        except Exception:
            _logger.exception('Error listing notifications')
            return self._error_response('Internal error', 'LIST_ERROR')

    @http.route('/social/api/notifications/<int:notif_id>/read', type='http', auth='user', methods=['POST'], csrf=False)
    def api_mark_read(self, notif_id, **kwargs):
        try:
            user = self._validate_auth()
            notif = request.env['club_social_profile.notification'].sudo().browse(notif_id)
            if not notif.exists() or notif.user_id.id != user.id:
                return self._error_response('Not found', 'NOT_FOUND', 404)
            notif.action_mark_read()
            return self._success_response({'read': True})
        except AccessError as e:
            return self._error_response(str(e), 'AUTH_ERROR', 401)
        except Exception:
            _logger.exception('Error marking notification read')
            return self._error_response('Internal error', 'READ_ERROR')

    @http.route('/social/api/notifications/read_all', type='http', auth='user', methods=['POST'], csrf=False)
    def api_mark_all_read(self, **kwargs):
        try:
            user = self._validate_auth()
            count = request.env['club_social_profile.notification'].sudo().mark_all_read(user.id)
            return self._success_response({'marked_read': count})
        except AccessError as e:
            return self._error_response(str(e), 'AUTH_ERROR', 401)
        except Exception:
            _logger.exception('Error marking all notifications read')
            return self._error_response('Internal error', 'READ_ALL_ERROR')

    def _notif_to_dict(self, notif):
        return {
            'id': notif.id,
            'type': notif.type,
            'body': notif.body,
            'is_read': notif.is_read,
            'read_at': notif.read_at.isoformat() if notif.read_at else None,
            'create_date': notif.create_date.isoformat() if notif.create_date else None,
            'url': notif.url or None,
            'ref_model': notif.ref_model or None,
            'ref_id': notif.ref_id or None,
            'actor': {
                'id': notif.actor_id.id,
                'name': notif.actor_id.name,
            } if notif.actor_id else None,
        }
