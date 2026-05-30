from odoo import fields, models


class ResUsersDigest(models.Model):
    """Tracks the last time the user received a reactivation digest.

    Used by social_notifications.digest_service to throttle: a user gets
    at most one digest per `social_notifications.digest_min_interval_days`
    even if they keep accumulating unread notifications.
    """
    _inherit = 'res.users'

    last_notification_digest_sent = fields.Datetime(
        string='Last digest sent',
        help='Timestamp of the last reactivation digest email sent to this user.',
        readonly=True,
    )
