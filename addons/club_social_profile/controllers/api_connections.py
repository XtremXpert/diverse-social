import logging

from odoo import http
from odoo.http import request
from odoo.exceptions import AccessError, ValidationError

from odoo.addons.social_base.controllers.mixins import SocialBaseMixin

_logger = logging.getLogger(__name__)


class ClubSocialConnectionAPI(SocialBaseMixin, http.Controller):

    @http.route('/social/api/connections', type='http', auth='user', methods=['POST'], csrf=False)
    def api_send_request(self, **kwargs):
        try:
            user = self._validate_auth()
            body = self._get_json_body()
            target_id = body.get('user_id') or kwargs.get('user_id')
            conn_type = body.get('connection_type', 'friend')
            if not target_id:
                return self._error_response('user_id required', 'INVALID_INPUT')

            conn = request.env['club_social_profile.connection'].sudo().create({
                'user_id': user.id,
                'connected_user_id': int(target_id),
                'connection_type': conn_type,
            })
            return self._success_response(self._conn_to_dict(conn))

        except ValidationError as e:
            return self._error_response(str(e), 'VALIDATION_ERROR')
        except AccessError as e:
            return self._error_response(str(e), 'AUTH_ERROR', 401)
        except Exception:
            _logger.exception('Error sending connection request')
            return self._error_response('Internal error', 'CREATE_ERROR')

    @http.route('/social/api/connections', type='http', auth='user', methods=['GET'], csrf=False)
    def api_list_connections(self, state='accepted', **kwargs):
        try:
            user = self._validate_auth()
            # Pending requests live as a single row on the sender's side
            # (connected_user_id is the recipient). The reciprocal row is only
            # created at acceptance. So when listing pending, we must look at
            # the receiving side; for accepted/rejected/blocked the user's own
            # row is enough.
            if state == 'pending':
                domain = [('connected_user_id', '=', user.id), ('state', '=', 'pending')]
            else:
                domain = [('user_id', '=', user.id)]
                if state:
                    domain.append(('state', '=', state))

            connections = request.env['club_social_profile.connection'].sudo().search(domain)
            return self._success_response({
                'connections': [self._conn_to_dict(c) for c in connections],
            })

        except AccessError as e:
            return self._error_response(str(e), 'AUTH_ERROR', 401)
        except Exception:
            _logger.exception('Error listing connections')
            return self._error_response('Internal error', 'LIST_ERROR')

    @http.route('/social/api/connections/<int:conn_id>/accept', type='http', auth='user', methods=['POST'], csrf=False)
    def api_accept(self, conn_id, **kwargs):
        try:
            user = self._validate_auth()
            conn = request.env['club_social_profile.connection'].sudo().browse(conn_id)
            if not conn.exists() or conn.connected_user_id != user:
                return self._error_response('Not found', 'NOT_FOUND', 404)

            conn.action_accept()
            return self._success_response({'state': conn.state})

        except AccessError as e:
            return self._error_response(str(e), 'AUTH_ERROR', 401)
        except Exception:
            _logger.exception('Error accepting connection')
            return self._error_response('Internal error', 'ACCEPT_ERROR')

    @http.route('/social/api/connections/<int:conn_id>/reject', type='http', auth='user', methods=['POST'], csrf=False)
    def api_reject(self, conn_id, **kwargs):
        try:
            user = self._validate_auth()
            conn = request.env['club_social_profile.connection'].sudo().browse(conn_id)
            if not conn.exists() or conn.connected_user_id != user:
                return self._error_response('Not found', 'NOT_FOUND', 404)

            conn.action_reject()
            return self._success_response({'state': conn.state})

        except AccessError as e:
            return self._error_response(str(e), 'AUTH_ERROR', 401)
        except Exception:
            _logger.exception('Error rejecting connection')
            return self._error_response('Internal error', 'REJECT_ERROR')

    def _conn_to_dict(self, conn):
        return {
            'id': conn.id,
            'user_id': conn.user_id.id,
            'connected_user_id': conn.connected_user_id.id,
            'connection_type': conn.connection_type,
            'state': conn.state,
            'create_date': conn.create_date.isoformat() if conn.create_date else None,
        }
