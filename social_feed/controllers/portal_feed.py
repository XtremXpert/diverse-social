from odoo.http import Controller, request, route


class FeedPortal(Controller):

    @route('/social/feed', auth='user', website=True, sitemap=False)
    def feed_page(self, **kw):
        """Shell for the aggregated feed.

        The actual feed items are loaded by JS via /social/api/feed —
        keeps the initial response light and lets infinite scroll handle
        pagination. Server only checks group membership + renders the
        chrome (sort tabs, preferences panel, scroll sentinel).
        """
        user = request.env.user
        if not user.has_group('social_base.group_social_user'):
            return request.redirect('/web')
        return request.render('social_feed.portal_feed_page', {
            'page_name': 'social_feed',
        })
