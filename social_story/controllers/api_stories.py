import logging

from odoo import http
from odoo.http import request
from odoo.exceptions import AccessError

from odoo.addons.social_base.controllers.mixins import SocialBaseMixin

_logger = logging.getLogger(__name__)


class SocialStoriesAPI(SocialBaseMixin, http.Controller):

    @http.route('/social/api/stories', type='http', auth='user', methods=['POST'], csrf=False)
    def api_create_story(self, **kwargs):
        try:
            user = self._validate_auth()
            body = self._get_json_body()
            title = body.get('title') or kwargs.get('title')
            attachment_ids = body.get('attachment_ids') or kwargs.get('attachment_ids', [])
            visibility = body.get('visibility') or kwargs.get('visibility')

            if not title or not attachment_ids:
                return self._error_response('Title and media required', 'INVALID_INPUT')

            vals = {'name': title, 'author_id': user.id}
            if visibility in ('public', 'members', 'connections'):
                vals['visibility'] = visibility
            story = request.env['social_story.story'].sudo().create(vals)

            for attachment_id in attachment_ids:
                att = request.env['ir.attachment'].sudo().browse(attachment_id)
                if att.exists() and att.create_uid.id == user.id and not att.res_id:
                    att.write({'res_model': 'social_story.story', 'res_id': story.id})

            return self._success_response(self._story_to_dict(story, user))

        except AccessError as e:
            return self._error_response(str(e), 'AUTH_ERROR', 401)
        except Exception:
            _logger.exception('Error creating story')
            return self._error_response('Internal error', 'CREATE_ERROR')

    @http.route('/social/api/stories', type='http', auth='user', methods=['GET'], csrf=False)
    def api_list_stories(self, **kwargs):
        try:
            user = self._validate_auth()
            stories = request.env['social_story.story'].sudo().search([('state', '=', 'active')])
            stories = stories.filtered(lambda s: s.is_accessible_by(user))
            return self._success_response({
                'stories': [self._story_to_dict(s, user) for s in stories],
                'total': len(stories),
            })

        except AccessError as e:
            return self._error_response(str(e), 'AUTH_ERROR', 401)
        except Exception:
            _logger.exception('Error listing stories')
            return self._error_response('Internal error', 'LIST_ERROR')

    @http.route('/social/api/stories/<int:story_id>/view', type='http', auth='user', methods=['POST'], csrf=False)
    def api_view_story(self, story_id, **kwargs):
        try:
            user = self._validate_auth()
            story = request.env['social_story.story'].sudo().browse(story_id)
            if not story.exists():
                return self._error_response('Story not found', 'NOT_FOUND', 404)
            if not story.is_accessible_by(user):
                return self._error_response('Access denied', 'FORBIDDEN', 403)
            story.mark_as_viewed(user)
            return self._success_response({'view_count': story.view_count})

        except AccessError as e:
            return self._error_response(str(e), 'AUTH_ERROR', 401)
        except Exception:
            _logger.exception('Error viewing story')
            return self._error_response('Internal error', 'VIEW_ERROR')

    def _story_to_dict(self, story, user):
        return {
            'id': story.id,
            'name': story.name,
            'author': {'id': story.author_id.id, 'name': story.author_id.name},
            'media_type': story.media_type,
            'create_date': story.create_date.isoformat() if story.create_date else None,
            'expires_at': story.expires_at.isoformat() if story.expires_at else None,
            'view_count': story.view_count,
            'viewed': user in story.viewer_ids,
            'state': story.state,
        }
