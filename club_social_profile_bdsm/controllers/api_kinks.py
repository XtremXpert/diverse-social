import logging

from odoo import http
from odoo.http import request
from odoo.exceptions import AccessError

from odoo.addons.social_base.controllers.mixins import SocialBaseMixin

_logger = logging.getLogger(__name__)


class ClubSocialKinkAPI(SocialBaseMixin, http.Controller):

    @http.route('/social/api/kinks', type='http', auth='user', methods=['GET'], csrf=False)
    def api_list_kinks(self, **kwargs):
        try:
            self._validate_auth()
            kinks = request.env['club_social_profile_bdsm.kink'].sudo().search([])
            return self._success_response({
                'kinks': [{'id': k.id, 'name': k.name, 'description': k.description} for k in kinks],
            })

        except AccessError as e:
            return self._error_response(str(e), 'AUTH_ERROR', 401)
        except Exception:
            _logger.exception('Error listing kinks')
            return self._error_response('Internal error', 'LIST_ERROR')

    @http.route('/social/api/kinks/request', type='http', auth='user', methods=['POST'], csrf=False)
    def api_request_kink(self, **kwargs):
        try:
            user = self._validate_auth()
            body = self._get_json_body()
            name = body.get('name') or kwargs.get('name')
            if not name:
                return self._error_response('name required', 'INVALID_INPUT')

            req = request.env['club_social_profile_bdsm.kink_request'].sudo().create({
                'name': name,
                'description': body.get('description'),
                'requester_id': user.id,
            })
            return self._success_response({'id': req.id, 'state': req.state})

        except AccessError as e:
            return self._error_response(str(e), 'AUTH_ERROR', 401)
        except Exception:
            _logger.exception('Error requesting kink')
            return self._error_response('Internal error', 'REQUEST_ERROR')

    @http.route('/social/api/profile/kinks', type='http', auth='user', methods=['POST'], csrf=False)
    def api_set_kink_level(self, **kwargs):
        try:
            user = self._validate_auth()
            body = self._get_json_body()
            kink_id = body.get('kink_id') or kwargs.get('kink_id')
            level = body.get('level') or kwargs.get('level', 'curieux')
            if not kink_id:
                return self._error_response('kink_id required', 'INVALID_INPUT')

            profile = request.env['club_social_profile.profile'].sudo().search(
                [('user_id', '=', user.id)], limit=1
            )
            if not profile:
                return self._error_response('Profile not found', 'NOT_FOUND', 404)

            KinkLevel = request.env['club_social_profile_bdsm.kink_level'].sudo()
            existing = KinkLevel.search([
                ('profile_id', '=', profile.id),
                ('kink_id', '=', int(kink_id)),
            ], limit=1)

            if existing:
                existing.write({'level': level})
                record = existing
            else:
                record = KinkLevel.create({
                    'profile_id': profile.id,
                    'kink_id': int(kink_id),
                    'level': level,
                })

            return self._success_response({
                'id': record.id,
                'kink_id': record.kink_id.id,
                'level': record.level,
            })

        except AccessError as e:
            return self._error_response(str(e), 'AUTH_ERROR', 401)
        except Exception:
            _logger.exception('Error setting kink level')
            return self._error_response('Internal error', 'SET_ERROR')

    @http.route('/social/api/profile/<int:profile_id>/compatibility', type='http', auth='user', methods=['GET'], csrf=False)
    def api_compatibility(self, profile_id, **kwargs):
        try:
            user = self._validate_auth()
            my_profile = request.env['club_social_profile.profile'].sudo().search(
                [('user_id', '=', user.id)], limit=1
            )
            other_profile = request.env['club_social_profile.profile'].sudo().browse(profile_id)

            if not my_profile or not other_profile.exists():
                return self._error_response('Profile not found', 'NOT_FOUND', 404)

            result = my_profile.compute_compatibility(other_profile)
            return self._success_response(result)

        except AccessError as e:
            return self._error_response(str(e), 'AUTH_ERROR', 401)
        except Exception:
            _logger.exception('Error computing compatibility')
            return self._error_response('Internal error', 'COMPAT_ERROR')
