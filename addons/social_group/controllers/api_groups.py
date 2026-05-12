import logging

from odoo import http
from odoo.http import request
from odoo.exceptions import AccessError, ValidationError

from odoo.addons.social_base.controllers.mixins import SocialBaseMixin

_logger = logging.getLogger(__name__)


class SocialGroupAPI(SocialBaseMixin, http.Controller):

    @http.route('/social/api/groups', type='http', auth='user', methods=['POST'], csrf=False)
    def api_create_group(self, **kwargs):
        try:
            user = self._validate_auth()
            body = self._get_json_body()
            name = body.get('name') or kwargs.get('name')
            if not name:
                return self._error_response('Name required', 'INVALID_INPUT')

            group = request.env['social_group.group'].sudo().create({
                'name': name,
                'description': body.get('description') or kwargs.get('description'),
                'privacy': body.get('privacy', 'private'),
                'join_type': body.get('join_type', 'approval'),
                'creator_id': user.id,
                'member_ids': [(4, user.id)],
                'admin_ids': [(4, user.id)],
            })
            return self._success_response(self._group_to_dict(group, user))

        except AccessError as e:
            return self._error_response(str(e), 'AUTH_ERROR', 401)
        except Exception:
            _logger.exception('Error creating group')
            return self._error_response('Internal error', 'CREATE_ERROR')

    @http.route('/social/api/groups', type='http', auth='user', methods=['GET'], csrf=False)
    def api_list_groups(self, limit=20, offset=0, **kwargs):
        try:
            user = self._validate_auth()
            domain = [('privacy', '!=', 'secret')]
            groups = request.env['social_group.group'].sudo().search(
                domain, limit=int(limit), offset=int(offset), order='member_count desc'
            )
            return self._success_response({
                'groups': [self._group_to_dict(g, user) for g in groups],
                'total': len(groups),
            })

        except AccessError as e:
            return self._error_response(str(e), 'AUTH_ERROR', 401)
        except Exception:
            _logger.exception('Error listing groups')
            return self._error_response('Internal error', 'LIST_ERROR')

    @http.route('/social/api/groups/<int:group_id>/join', type='http', auth='user', methods=['POST'], csrf=False)
    def api_join_group(self, group_id, **kwargs):
        try:
            self._validate_auth()
            group = request.env['social_group.group'].sudo().browse(group_id)
            if not group.exists():
                return self._error_response('Group not found', 'NOT_FOUND', 404)

            result = group.with_user(request.env.user).action_join()
            return self._success_response({'action': result.get('params', {}).get('type', 'ok')})

        except ValidationError as e:
            return self._error_response(str(e), 'VALIDATION_ERROR')
        except AccessError as e:
            return self._error_response(str(e), 'AUTH_ERROR', 401)
        except Exception:
            _logger.exception('Error joining group')
            return self._error_response('Internal error', 'JOIN_ERROR')

    @http.route('/social/api/groups/<int:group_id>/leave', type='http', auth='user', methods=['POST'], csrf=False)
    def api_leave_group(self, group_id, **kwargs):
        try:
            self._validate_auth()
            group = request.env['social_group.group'].sudo().browse(group_id)
            if not group.exists():
                return self._error_response('Group not found', 'NOT_FOUND', 404)

            group.with_user(request.env.user).action_leave()
            return self._success_response({'left': True})

        except ValidationError as e:
            return self._error_response(str(e), 'VALIDATION_ERROR')
        except AccessError as e:
            return self._error_response(str(e), 'AUTH_ERROR', 401)
        except Exception:
            _logger.exception('Error leaving group')
            return self._error_response('Internal error', 'LEAVE_ERROR')

    def _group_to_dict(self, group, user):
        return {
            'id': group.id,
            'name': group.name,
            'description': group.description,
            'privacy': group.privacy,
            'join_type': group.join_type,
            'member_count': group.member_count,
            'post_count': group.post_count,
            'is_member': group.is_member(user),
            'is_admin': group.is_admin(user),
        }
