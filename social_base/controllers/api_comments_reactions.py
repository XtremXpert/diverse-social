import logging

from odoo import http
from odoo.http import request
from odoo.exceptions import AccessError

from .mixins import SocialBaseMixin

_logger = logging.getLogger(__name__)


class SocialCommentsAPI(SocialBaseMixin, http.Controller):

    @http.route('/social/api/posts/<int:post_id>/comments', type='http', auth='user', methods=['POST'], csrf=False)
    def api_create_comment(self, post_id, **kwargs):
        try:
            user = self._validate_auth()
            body = self._get_json_body()
            content = body.get('content') or kwargs.get('content')
            parent_id = body.get('parent_id') or kwargs.get('parent_id')

            if not content:
                return self._error_response('Content required', 'INVALID_INPUT')

            post = self._get_visible_post(post_id, user)
            if not post:
                return self._error_response('Post not found', 'NOT_FOUND', 404)

            vals = {'content': content, 'author_id': user.id, 'post_id': post_id}
            if parent_id:
                vals['parent_id'] = int(parent_id)

            comment = request.env['social_base.comment'].sudo().create(vals)
            return self._success_response(self._comment_to_dict(comment))

        except AccessError as e:
            return self._error_response(str(e), 'AUTH_ERROR', 401)
        except Exception:
            _logger.exception('Error creating comment')
            return self._error_response('Internal error', 'CREATE_ERROR')

    @http.route('/social/api/posts/<int:post_id>/comments', type='http', auth='user', methods=['GET'], csrf=False)
    def api_list_comments(self, post_id, **kwargs):
        try:
            user = self._validate_auth()
            post = self._get_visible_post(post_id, user)
            if not post:
                return self._error_response('Post not found', 'NOT_FOUND', 404)

            comments = request.env['social_base.comment'].sudo().search([
                ('post_id', '=', post_id),
                ('parent_id', '=', False),
                ('state', '=', 'published'),
            ], order='create_date asc')

            return self._success_response({
                'comments': [self._comment_to_dict(c) for c in comments],
                'total': len(comments),
            })

        except AccessError as e:
            return self._error_response(str(e), 'AUTH_ERROR', 401)
        except Exception:
            _logger.exception('Error listing comments')
            return self._error_response('Internal error', 'LIST_ERROR')

    @http.route('/social/api/comments/<int:comment_id>/replies', type='http', auth='user', methods=['GET'], csrf=False)
    def api_list_replies(self, comment_id, **kwargs):
        try:
            user = self._validate_auth()
            comment = self._get_visible_comment(comment_id, user)
            if not comment:
                return self._error_response('Comment not found', 'NOT_FOUND', 404)

            replies = request.env['social_base.comment'].sudo().search([
                ('parent_id', '=', comment_id),
                ('state', '=', 'published'),
            ], order='create_date asc')

            return self._success_response({'replies': [self._comment_to_dict(r) for r in replies], 'total': len(replies)})

        except AccessError as e:
            return self._error_response(str(e), 'AUTH_ERROR', 401)
        except Exception:
            _logger.exception('Error listing replies')
            return self._error_response('Internal error', 'LIST_ERROR')

    @http.route('/social/api/comments/<int:comment_id>', type='http', auth='user', methods=['DELETE'], csrf=False)
    def api_delete_comment(self, comment_id, **kwargs):
        try:
            user = self._validate_auth()
            comment = request.env['social_base.comment'].sudo().browse(comment_id)
            if not comment.exists():
                return self._error_response('Comment not found', 'NOT_FOUND', 404)
            if comment.author_id != user and not user.has_group('social_base.group_social_admin'):
                return self._error_response('Access denied', 'ACCESS_DENIED', 403)

            comment.action_delete()
            return self._success_response({'deleted': True})

        except AccessError as e:
            return self._error_response(str(e), 'AUTH_ERROR', 401)
        except Exception:
            _logger.exception('Error deleting comment')
            return self._error_response('Internal error', 'DELETE_ERROR')

    def _comment_to_dict(self, comment):
        return {
            'id': comment.id,
            'content': comment.content,
            'author': {'id': comment.author_id.id, 'name': comment.author_id.name},
            'create_date': comment.create_date.isoformat() if comment.create_date else None,
            'like_count': comment.like_count,
            'parent_id': comment.parent_id.id if comment.parent_id else None,
            'reply_count': len(comment.child_ids),
        }


class SocialReactionsAPI(SocialBaseMixin, http.Controller):

    @http.route('/social/api/posts/<int:post_id>/reactions', type='http', auth='user', methods=['POST'], csrf=False)
    def api_add_post_reaction(self, post_id, **kwargs):
        try:
            user = self._validate_auth()
            body = self._get_json_body()
            reaction_type = body.get('type') or kwargs.get('type')
            if not reaction_type:
                return self._error_response('Reaction type required', 'INVALID_INPUT')

            post = self._get_visible_post(post_id, user)
            if not post:
                return self._error_response('Post not found', 'NOT_FOUND', 404)

            existing = post.reaction_ids.filtered(lambda r: r.user_id == user)
            if existing:
                if existing.type == reaction_type:
                    existing.unlink()
                    return self._success_response({'action': 'removed', 'like_count': post.like_count})
                existing.write({'type': reaction_type})
                return self._success_response({'action': 'updated', 'type': reaction_type, 'like_count': post.like_count})

            request.env['social_base.reaction'].sudo().create({
                'post_id': post_id, 'user_id': user.id, 'type': reaction_type,
            })
            return self._success_response({'action': 'added', 'type': reaction_type, 'like_count': post.like_count})

        except AccessError as e:
            return self._error_response(str(e), 'AUTH_ERROR', 401)
        except Exception:
            _logger.exception('Error adding reaction')
            return self._error_response('Internal error', 'REACTION_ERROR')

    @http.route('/social/api/comments/<int:comment_id>/reactions', type='http', auth='user', methods=['POST'], csrf=False)
    def api_add_comment_reaction(self, comment_id, **kwargs):
        try:
            user = self._validate_auth()
            body = self._get_json_body()
            reaction_type = body.get('type') or kwargs.get('type')
            if not reaction_type:
                return self._error_response('Reaction type required', 'INVALID_INPUT')

            comment = self._get_visible_comment(comment_id, user)
            if not comment:
                return self._error_response('Comment not found', 'NOT_FOUND', 404)

            existing = comment.reaction_ids.filtered(lambda r: r.user_id == user)
            if existing:
                if existing.type == reaction_type:
                    existing.unlink()
                    return self._success_response({'action': 'removed', 'like_count': comment.like_count})
                existing.write({'type': reaction_type})
                return self._success_response({'action': 'updated', 'type': reaction_type, 'like_count': comment.like_count})

            request.env['social_base.reaction'].sudo().create({
                'comment_id': comment_id, 'user_id': user.id, 'type': reaction_type,
            })
            return self._success_response({'action': 'added', 'type': reaction_type, 'like_count': comment.like_count})

        except AccessError as e:
            return self._error_response(str(e), 'AUTH_ERROR', 401)
        except Exception:
            _logger.exception('Error adding reaction')
            return self._error_response('Internal error', 'REACTION_ERROR')

    @http.route('/social/api/posts/<int:post_id>/reactions', type='http', auth='user', methods=['GET'], csrf=False)
    def api_list_post_reactions(self, post_id, **kwargs):
        try:
            user = self._validate_auth()
            post = self._get_visible_post(post_id, user)
            if not post:
                return self._error_response('Post not found', 'NOT_FOUND', 404)

            by_type = {}
            for r in post.reaction_ids:
                by_type.setdefault(r.type, []).append({'user_id': r.user_id.id, 'user_name': r.user_id.name})

            return self._success_response({
                'reactions': [{'type': t, 'count': len(u), 'users': u[:5]} for t, u in by_type.items()],
                'total': len(post.reaction_ids),
            })

        except AccessError as e:
            return self._error_response(str(e), 'AUTH_ERROR', 401)
        except Exception:
            _logger.exception('Error listing reactions')
            return self._error_response('Internal error', 'LIST_ERROR')
