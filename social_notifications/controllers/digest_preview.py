from odoo.http import Controller, request, route


# Stable filler shown when the user has no unread notifications. Lets
# them see what the digest would look like before they ever miss one.
_DUMMY_SUMMARY = [
    {
        'type': 'new_message',
        'count': 3,
        'label': 'private messages',
        'sample_names': ['Alice', 'Bob'],
        'extra_count': 1,
        'latest_url': '#',
    },
    {
        'type': 'connection_request',
        'count': 1,
        'label': 'connection request',
        'sample_names': ['Carol'],
        'extra_count': 0,
        'latest_url': '#',
    },
    {
        'type': 'post_like',
        'count': 5,
        'label': 'reactions to your posts',
        'sample_names': ['Dana', 'Eve', 'Frank'],
        'extra_count': 2,
        'latest_url': '#',
    },
]


class DigestPreview(Controller):
    """Lets a user see the digest email they would receive.

    Renders the real Qweb template with the user's actual current
    summary, or a stable placeholder when they have nothing pending.
    The point is to make the privacy contract visible *before* the
    cron sends anything — what the digest will leak into the inbox is
    no longer abstract.
    """

    @route('/my/profile/digest_preview', auth='user', website=True, sitemap=False)
    def digest_preview(self, **kw):
        user = request.env.user
        if user._is_public():
            return request.redirect('/web/login')

        Service = request.env['social_notifications.digest_service']
        summary = Service._summary_for_user(user)
        is_real = bool(summary)
        if not is_real:
            summary = _DUMMY_SUMMARY

        total = sum(g['count'] for g in summary)
        base_url = request.env['ir.config_parameter'].sudo().get_param('web.base.url', '')
        unsub_token = Service._unsubscribe_token(user.id)
        unsubscribe_url = f'{base_url}/notifications/digest/unsubscribe/{user.id}/{unsub_token}'

        return request.render('social_notifications.digest_preview_page', {
            'user': user,
            'summary': summary,
            'total': total,
            'is_real': is_real,
            'base_url': base_url,
            'unsubscribe_url': unsubscribe_url,
        })
