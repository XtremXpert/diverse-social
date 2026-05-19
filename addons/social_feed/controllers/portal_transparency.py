from odoo import http
from odoo.http import request


class FeedTransparency(http.Controller):

    @http.route(['/my/feed/transparency'], type='http', auth='user', website=True)
    def portal_feed_transparency(self, **kw):
        """Explain the algorithmic ranking and personalization to the user."""
        user = request.env.user

        # Build explanation of the current user's feed context
        FeedService = request.env['social_feed.service'].sudo()
        ctx = FeedService._feed_context()

        values = {
            'page_name': 'feed_transparency',
            'user': user,
            'connection_count': len(ctx.get('connection_user_ids', [])),
            'blocked_count': len(ctx.get('blocked_ids', [])),
            'group_count': len(ctx.get('member_group_ids', [])),
            'circle_count': len(ctx.get('circle_ids', [])),
            'sort_mode': kw.get('sort', 'recent'),
            'show_algorithm': True,
        }
        return request.render('social_feed.portal_feed_transparency', values)
