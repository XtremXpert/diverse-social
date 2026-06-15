from odoo.addons.portal.controllers.portal import CustomerPortal, pager as portal_pager
from odoo.http import request, route

_PAGE_SIZE = 30


class NotificationsPortal(CustomerPortal):

    @route(['/social/notifications', '/social/notifications/page/<int:page>'], auth='user', website=True, sitemap=False)
    def notifications_page(self, page=1, filter='all', **kw):
        user = request.env.user
        page = max(1, int(page))

        domain = [('user_id', '=', user.id)]
        if filter == 'unread':
            domain.append(('is_read', '=', False))

        Notif = request.env['club_social_profile.notification'].sudo()
        total = Notif.search_count(domain)
        pager = portal_pager(
            url='/social/notifications',
            url_args={'filter': filter},
            total=total,
            page=page,
            step=_PAGE_SIZE,
        )
        notifications = Notif.search(
            domain,
            order='create_date desc',
            limit=_PAGE_SIZE,
            offset=pager['offset'],
        )
        unread_count = Notif.search_count([('user_id', '=', user.id), ('is_read', '=', False)])

        return request.render('social_notifications.portal_notifications_page', {
            'notifications': notifications,
            'pager': pager,
            'total': total,
            'filter': filter,
            'unread_count': unread_count,
        })
