from odoo import fields, models


class PwaSubscription(models.Model):
    """A registered web-push endpoint for a user's browser/device.

    One user → many subscriptions (phone + laptop + work browser, etc.).
    Each subscription stores the three opaque tokens returned by the
    PushManager.subscribe() Promise. We don't introspect them; only the
    push backend does, when delivering a notification.
    """
    _name = 'social_pwa.subscription'
    _description = 'Web Push Subscription'
    _order = 'create_date desc'

    user_id = fields.Many2one('res.users', required=True, ondelete='cascade', index=True)
    endpoint = fields.Char(required=True)
    p256dh = fields.Char(required=True)
    auth = fields.Char(required=True)
    user_agent = fields.Char()
    last_seen = fields.Datetime(default=fields.Datetime.now)

    _sql_constraints = [
        ('endpoint_unique', 'unique(endpoint)',
         'A subscription with this endpoint already exists.'),
    ]
