import logging

from odoo.http import request
from odoo.exceptions import AccessError

from odoo.addons.social_group.controllers.api_posts import SocialPostAPIGroup

_logger = logging.getLogger(__name__)


class SocialPostAPICategory(SocialPostAPIGroup):

    @staticmethod
    def _resolve_category(body, kwargs, env):
        """Return (category_recordset_or_empty, error_message_or_None).

        Precedence: ``category_code`` over ``category_id`` (code is the
        cross-DB stable identifier). Empty input ⇒ no category. Unknown
        code/id ⇒ caller-visible 400.
        """
        code = body.get('category_code') if body else None
        if code in (None, '', False):
            code = kwargs.get('category_code')

        if code:
            category = env['social_post_categories.category'].sudo().search(
                [('code', '=', code), ('active', '=', True)], limit=1,
            )
            if not category:
                return env['social_post_categories.category'], (
                    f"Unknown category_code: {code}"
                )
            return category, None

        raw_id = body.get('category_id') if body else None
        if raw_id in (None, '', False):
            raw_id = kwargs.get('category_id')
        if raw_id in (None, '', False):
            return env['social_post_categories.category'], None
        try:
            cid = int(raw_id)
        except (TypeError, ValueError):
            return env['social_post_categories.category'], 'Invalid category_id'
        category = env['social_post_categories.category'].sudo().browse(cid)
        if not category.exists() or not category.active:
            return env['social_post_categories.category'], (
                f"Unknown category_id: {cid}"
            )
        return category, None

    def api_create_post(self, **kwargs):
        try:
            user = self._validate_auth()
            body = self._get_json_body()
            content = body.get('content') or kwargs.get('content')
            visibility = body.get('visibility') or kwargs.get('visibility', 'members')
            attachment_ids = body.get('attachment_ids') or kwargs.get('attachment_ids', [])

            if not content and not attachment_ids:
                return self._error_response('Content or attachments required', 'INVALID_INPUT')

            # Optional group_id support if social_group is installed.
            vals = {
                'content': content,
                'author_id': user.id,
                'visibility': visibility,
            }
            group_id = None
            try:
                group_id = self._resolve_group_id(body, kwargs)
            except AttributeError:
                # social_group not installed
                pass
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

            # Category resolution
            category, err = self._resolve_category(body, kwargs, request.env)
            if err:
                return self._error_response(err, 'INVALID_INPUT')
            if category:
                vals['category_id'] = category.id

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

    def _post_to_dict(self, post, user):
        data = super()._post_to_dict(post, user)
        if post.category_id:
            data['category'] = {
                'id': post.category_id.id,
                'code': post.category_id.code,
                'name': post.category_id.name,
                'color': post.category_id.color or None,
                'icon': post.category_id.icon or None,
            }
        else:
            data['category'] = None
        return data
