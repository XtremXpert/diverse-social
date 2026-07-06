import logging

from odoo import http
from odoo.http import request
from odoo.exceptions import AccessError

from .mixins import SocialBaseMixin

_logger = logging.getLogger(__name__)


class SocialPostAPI(SocialBaseMixin, http.Controller):

    @http.route('/social/api/posts', type='http', auth='user', methods=['POST'], csrf=False)
    def api_create_post(self, **kwargs):
        try:
            user = self._validate_auth()
            body = self._get_json_body()
            content = body.get('content') or kwargs.get('content')
            visibility = body.get('visibility') or kwargs.get('visibility', 'members')
            attachment_ids = body.get('attachment_ids') or kwargs.get('attachment_ids', [])

            if not content and not attachment_ids:
                return self._error_response('Content or attachments required', 'INVALID_INPUT')

            post = request.env['social_base.post'].sudo().create({
                'content': content,
                'author_id': user.id,
                'visibility': visibility,
            })

            for attachment_id in attachment_ids:
                att = request.env['ir.attachment'].sudo().browse(attachment_id)
                if att.exists() and att.create_uid.id == user.id and not att.res_id:
                    att.write({'res_model': 'social_base.post', 'res_id': post.id})

            return self._success_response(self._post_to_dict(post, user))

        except AccessError as e:
            return self._error_response(str(e), 'AUTH_ERROR', 401)
        except Exception:
            _logger.exception('Error creating post')
            return self._error_response('Internal error', 'CREATE_ERROR')

    @http.route('/social/api/posts', type='http', auth='user', methods=['GET'], csrf=False)
    def api_list_posts(self, limit=20, offset=0, user_id=None, **kwargs):
        try:
            user = self._validate_auth()
            domain = [
                ('state', '=', 'published'),
                ('visibility', 'in', ['public', 'members']),
            ]
            if user_id:
                domain.append(('author_id', '=', int(user_id)))

            posts = request.env['social_base.post'].sudo().search(
                domain, limit=int(limit), offset=int(offset), order='create_date desc'
            )
            return self._success_response({
                'posts': [self._post_to_dict(p, user) for p in posts],
                'total': len(posts),
                'limit': int(limit),
                'offset': int(offset),
            })

        except AccessError as e:
            return self._error_response(str(e), 'AUTH_ERROR', 401)
        except Exception:
            _logger.exception('Error listing posts')
            return self._error_response('Internal error', 'LIST_ERROR')

    @http.route('/social/api/posts/<int:post_id>', type='http', auth='user', methods=['GET'], csrf=False)
    def api_get_post(self, post_id, **kwargs):
        try:
            user = self._validate_auth()
            post = self._get_visible_post(post_id, user)
            if not post:
                return self._error_response('Post not found', 'NOT_FOUND', 404)

            post.increment_view_count()
            data = self._post_to_dict(post, user)
            data['attachments'] = [
                {'id': a.id, 'name': a.name, 'url': f'/web/content/{a.id}', 'mimetype': a.mimetype}
                for a in post.attachment_ids
            ]
            return self._success_response(data)

        except AccessError as e:
            return self._error_response(str(e), 'AUTH_ERROR', 401)
        except Exception:
            _logger.exception('Error getting post')
            return self._error_response('Internal error', 'GET_ERROR')

    @http.route('/social/api/posts/<int:post_id>', type='http', auth='user', methods=['PUT'], csrf=False)
    def api_update_post(self, post_id, **kwargs):
        try:
            user = self._validate_auth()
            post = request.env['social_base.post'].sudo().browse(post_id)
            if not post.exists():
                return self._error_response('Post not found', 'NOT_FOUND', 404)
            if post.author_id != user:
                return self._error_response('Access denied', 'ACCESS_DENIED', 403)

            body = self._get_json_body()
            vals = {}
            if body.get('content'):
                vals['content'] = body['content']
            if body.get('visibility'):
                vals['visibility'] = body['visibility']
            if vals:
                post.write(vals)

            return self._success_response({'id': post.id, 'content': post.content, 'visibility': post.visibility})

        except AccessError as e:
            return self._error_response(str(e), 'AUTH_ERROR', 401)
        except Exception:
            _logger.exception('Error updating post')
            return self._error_response('Internal error', 'UPDATE_ERROR')

    @http.route('/social/api/posts/<int:post_id>', type='http', auth='user', methods=['DELETE'], csrf=False)
    def api_delete_post(self, post_id, **kwargs):
        try:
            user = self._validate_auth()
            post = request.env['social_base.post'].sudo().browse(post_id)
            if not post.exists():
                return self._error_response('Post not found', 'NOT_FOUND', 404)
            if post.author_id != user and not user.has_group('social_base.group_social_admin'):
                return self._error_response('Access denied', 'ACCESS_DENIED', 403)

            post.unlink()
            return self._success_response({'deleted': True})

        except AccessError as e:
            return self._error_response(str(e), 'AUTH_ERROR', 401)
        except Exception:
            _logger.exception('Error deleting post')
            return self._error_response('Internal error', 'DELETE_ERROR')

    @http.route('/social/api/posts/<int:post_id>/share', type='http', auth='user', methods=['POST'], csrf=False)
    def api_share_post(self, post_id, **kwargs):
        try:
            user = self._validate_auth()
            post = self._get_visible_post(post_id, user)
            if not post:
                return self._error_response('Post not found', 'NOT_FOUND', 404)
            post.increment_share_count()
            return self._success_response({'id': post.id, 'share_count': post.share_count})

        except AccessError as e:
            return self._error_response(str(e), 'AUTH_ERROR', 401)
        except Exception:
            _logger.exception('Error sharing post')
            return self._error_response('Internal error', 'SHARE_ERROR')

    def _post_to_dict(self, post, user):
        reaction = post.reaction_ids.filtered(lambda r: r.user_id == user)
        return {
            'id': post.id,
            'content': post.content,
            'author': {'id': post.author_id.id, 'name': self._member_display_name(post.author_id)},
            'create_date': post.create_date.isoformat() if post.create_date else None,
            'like_count': post.like_count,
            'comment_count': post.comment_count,
            'view_count': post.view_count,
            'share_count': post.share_count,
            'media_type': post.media_type,
            'visibility': post.visibility,
            'is_pinned': post.is_pinned,
            'user_reaction': reaction.type if reaction else None,
        }
