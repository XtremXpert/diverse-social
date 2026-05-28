from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

# Same set as VALID_TYPES in feed_service.py — kept in sync intentionally.
FEED_TYPES = [
    ('post', 'Posts'),
    ('story', 'Stories'),
    ('event', 'Events'),
    ('event_registration', 'Connection RSVPs'),
    ('proposal', 'Proposals'),
    ('gallery', 'Galleries'),
]

BOOST_MIN = 0.1
BOOST_MAX = 5.0


class FeedUserPreference(models.Model):
    """Per-user multiplier on a feed item type's relevance score.

    Sparse storage: a missing row means "default boost = 1.0". Users
    only persist preferences they actively changed via the UI, so the
    table stays small.

    Boost range is bounded so a malicious or buggy client can't push
    a type to dominate or vanish entirely.
    """
    _name = 'social_feed.user_preference'
    _description = 'Feed type boost per user'

    user_id = fields.Many2one('res.users', required=True, ondelete='cascade', index=True)
    item_type = fields.Selection(FEED_TYPES, required=True)
    boost_factor = fields.Float(default=1.0, required=True,
                                help='1.0 = unchanged. Range %s–%s.' % (BOOST_MIN, BOOST_MAX))

    _sql_constraints = [
        ('user_type_unique', 'unique(user_id, item_type)',
         'Only one preference per (user, type).'),
    ]

    @api.constrains('boost_factor')
    def _check_boost_range(self):
        for r in self:
            if not (BOOST_MIN <= r.boost_factor <= BOOST_MAX):
                raise ValidationError(_(
                    'Boost must be between %(low)s and %(high)s.',
                    low=BOOST_MIN, high=BOOST_MAX,
                ))

    @api.model
    def set_boost(self, user_id, item_type, boost_factor):
        """Idempotent upsert. Clamps the boost into the allowed range."""
        clamped = max(BOOST_MIN, min(BOOST_MAX, float(boost_factor)))
        existing = self.search([
            ('user_id', '=', user_id),
            ('item_type', '=', item_type),
        ], limit=1)
        if existing:
            existing.boost_factor = clamped
            return existing
        return self.create({
            'user_id': user_id,
            'item_type': item_type,
            'boost_factor': clamped,
        })

    @api.model
    def boosts_for_user(self, user_id):
        """Return {item_type: boost_factor} for the user. Missing types absent."""
        recs = self.search([('user_id', '=', user_id)])
        return {r.item_type: r.boost_factor for r in recs}
