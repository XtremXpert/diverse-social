import json

from odoo.http import request
from odoo.exceptions import AccessError


class SocialBaseMixin:
    """Shared utilities for social_base controllers."""

    def _validate_auth(self):
        if not request.env.user or request.env.user.id == request.env.ref('base.public_user').id:
            raise AccessError('Authentication required')
        return request.env.user

    def _json_response(self, data, status=200):
        return request.make_json_response(data, status=status)

    def _success_response(self, data):
        return self._json_response({'success': True, 'data': data})

    def _error_response(self, message, code='ERROR', status=400):
        return self._json_response({'success': False, 'error': message, 'code': code}, status=status)

    def _get_json_body(self):
        try:
            data = request.httprequest.get_data(as_text=True)
            return json.loads(data) if data else {}
        except (ValueError, TypeError):
            return {}

    def _member_display_name(self, user):
        """Nom affichable d'un membre : pseudonyme (stealth_name) si le module
        de profils est installé, jamais le vrai nom. social_base ne dépend pas
        de club_social_profile, d'où le garde `in env` (un recordset vide est
        falsy — ne pas utiliser env.get())."""
        if not user:
            return None
        if 'club_social_profile.profile' in request.env:
            return request.env['club_social_profile.profile']._display_name_for_user(user)
        return user.name

    def _visibility_params(self, user):
        """Gather params for social_base.post._visibility_domain defensively.

        social_base does not depend on social_safety / club_social_profile /
        social_group, so those models may be absent. When present we use them
        to compute the user's real connections, groups and blocks; otherwise
        we fall back to empty lists (safe and more restrictive)."""
        env = request.env
        params = {
            'connection_user_ids': [],
            'member_group_ids': [],
            'blocked_user_ids': [],
        }
        if 'club_social_profile.connection' in env:
            params['connection_user_ids'] = env['club_social_profile.connection'].sudo().search([
                ('user_id', '=', user.id),
                ('state', '=', 'accepted'),
            ]).mapped('connected_user_id.id')
        if 'social_group.group' in env:
            params['member_group_ids'] = env['social_group.group'].sudo().search(
                [('member_ids', 'in', [user.id])]
            ).ids
        if 'social_safety.block' in env:
            params['blocked_user_ids'] = env['social_safety.block'].sudo().get_blocked_ids_for(user)
        return params

    def _get_visible_post(self, post_id, user):
        """Return the post if visible to `user`, else an empty recordset.

        Visibility is enforced through social_base.post._visibility_domain (the
        single source of truth). The author always retains access to their own
        post, regardless of state, so drafts/moderation remain reachable."""
        Post = request.env['social_base.post'].sudo()
        domain = [('id', '=', post_id)] + Post._visibility_domain(
            user, **self._visibility_params(user)
        )
        post = Post.search(domain, limit=1)
        if post:
            return post
        own = Post.browse(post_id)
        if own.exists() and own.author_id.id == user.id:
            return own
        return Post.browse()

    def _get_visible_comment(self, comment_id, user):
        """Return the comment if its parent post is visible to `user`."""
        Comment = request.env['social_base.comment'].sudo()
        comment = Comment.browse(comment_id)
        if not comment.exists():
            return Comment.browse()
        if not self._get_visible_post(comment.post_id.id, user):
            return Comment.browse()
        return comment
