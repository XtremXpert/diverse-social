import logging

from odoo.http import request
from odoo.exceptions import AccessError

from odoo.addons.social_base.controllers.api_posts import SocialPostAPI

_logger = logging.getLogger(__name__)


class SocialPostAPIGroup(SocialPostAPI):

    @staticmethod
    def _resolve_group_id(body, kwargs):
        raw = body.get('group_id') if body else None
        if raw is None:
            raw = kwargs.get('group_id')
        if raw in (None, '', False):
            return None
        try:
            return int(raw)
        except (TypeError, ValueError):
            return False

    def _can_post_in_group(self, group, user):
        """A user can post in a group if they are a member, or admin of it."""
        if user.has_group('social_base.group_social_admin'):
            return True
        return user in (group.member_ids | group.admin_ids)

    def api_create_post(self, **kwargs):
        try:
            user = self._validate_auth()
            body = self._get_json_body()
            content = body.get('content') or kwargs.get('content')
            visibility = body.get('visibility') or kwargs.get('visibility', 'members')
            attachment_ids = body.get('attachment_ids') or kwargs.get('attachment_ids', [])
            group_id = self._resolve_group_id(body, kwargs)

            if not content and not attachment_ids:
                return self._error_response('Content or attachments required', 'INVALID_INPUT')

            vals = {
                'content': content,
                'author_id': user.id,
                'visibility': visibility,
            }
            if group_id is False:
                return self._error_response('Invalid group_id', 'INVALID_INPUT')
            if group_id:
                group = request.env['social_group.group'].sudo().browse(group_id)
                if not group.exists():
                    return self._error_response('Group not found', 'NOT_FOUND', 404)
                if not self._can_post_in_group(group, user):
                    return self._error_response(
                        'You must join this group before posting in it',
                        'ACCESS_DENIED', 403,
                    )
                vals['group_id'] = group.id

            post = request.env['social_base.post'].sudo().create(vals)

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

    def api_list_posts(self, limit=20, offset=0, user_id=None, group_id=None, **kwargs):
        try:
            user = self._validate_auth()
            domain = [
                ('state', '=', 'published'),
                ('visibility', 'in', ['public', 'members']),
            ]
            if user_id:
                domain.append(('author_id', '=', int(user_id)))
            if group_id:
                gid = int(group_id)
                group = request.env['social_group.group'].sudo().browse(gid)
                if not group.exists():
                    return self._error_response('Group not found', 'NOT_FOUND', 404)
                # Secret groups are member-only. Public/private list posts to anyone.
                if group.privacy == 'secret' and not self._can_post_in_group(group, user):
                    return self._error_response('Access denied', 'ACCESS_DENIED', 403)
                domain.append(('group_id', '=', gid))
            else:
                # Without an explicit group filter, hide in-group posts from the
                # global feed. They're shown when requested per-group.
                domain.append(('group_id', '=', False))

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

    def _post_to_dict(self, post, user):
        data = super()._post_to_dict(post, user)
        if post.group_id:
            data['group'] = {'id': post.group_id.id, 'name': post.group_id.name}
        else:
            data['group'] = None
        return data
