from odoo.http import Controller, request, route


class DigestUnsubscribe(Controller):
    """One-click unsubscribe from reactivation digest emails.

    The link is sent in the digest email itself, signed with an HMAC
    derived from the database secret. Reaching the URL — even unauth'd —
    disables future digests for that user. Designed to be safe to put in
    an email: the token doesn't grant any other capability, and the
    write is idempotent.
    """

    @route('/notifications/digest/unsubscribe/<int:user_id>/<string:token>',
           auth='public', website=True, sitemap=False, csrf=False)
    def unsubscribe(self, user_id, token, **kw):
        Service = request.env['social_notifications.digest_service'].sudo()
        if not Service._verify_unsubscribe_token(user_id, token):
            return request.render('social_notifications.digest_unsubscribe_invalid')

        Profile = request.env['club_social_profile.profile'].sudo()
        profile = Profile.search([('user_id', '=', user_id)], limit=1)
        if profile and profile.digest_email_enabled:
            profile.digest_email_enabled = False

        return request.render('social_notifications.digest_unsubscribed_page')
