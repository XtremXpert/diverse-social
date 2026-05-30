import logging
from datetime import timedelta

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

# Items older than this are auto-purged. The marker only matters while
# the item is plausibly still in someone's feed buffer; after that, the
# row is dead weight.
_RETENTION_DAYS = 30


class FeedReadMarker(models.Model):
    """Tracks which (item_type, item_id) a user has marked as read.

    Heterogeneous reference — Posts, Stories, Events, Proposals and
    Galleries each have their own id space, so we keep (type, id) as
    the composite reference instead of a polymorphic FK.

    The presence of a row is the signal: 'read'. Absence = unread. We
    never store explicit 'unread' rows.
    """
    _name = 'social_feed.read_marker'
    _description = 'Feed read marker'
    _order = 'read_at desc'

    user_id = fields.Many2one('res.users', required=True, ondelete='cascade', index=True)
    item_type = fields.Char(required=True, index=True)
    item_id = fields.Integer(required=True)
    read_at = fields.Datetime(default=fields.Datetime.now, required=True)

    _sql_constraints = [
        ('user_item_unique', 'unique(user_id, item_type, item_id)',
         'Already marked as read.'),
    ]

    # ── Bulk helpers ─────────────────────────────────────────────────────────

    @api.model
    def mark_read(self, user_id, item_type, item_id):
        """Idempotent — re-marking an already-read item is a no-op."""
        existing = self.search([
            ('user_id', '=', user_id),
            ('item_type', '=', item_type),
            ('item_id', '=', item_id),
        ], limit=1)
        if existing:
            return existing
        return self.create({
            'user_id': user_id, 'item_type': item_type, 'item_id': item_id,
        })

    @api.model
    def mark_unread(self, user_id, item_type, item_id):
        self.search([
            ('user_id', '=', user_id),
            ('item_type', '=', item_type),
            ('item_id', '=', item_id),
        ]).unlink()

    @api.model
    def read_set_for_user(self, user_id, items=None):
        """Return a set of (item_type, item_id) tuples this user has read.

        If `items` is provided (iterable of dicts with 'item_type' and 'id'),
        the query is scoped to just those — one round trip regardless of
        feed size.
        """
        domain = [('user_id', '=', user_id)]
        if items is not None:
            # Group by type so the IN clause stays per-type (item ids
            # collide across types).
            from collections import defaultdict
            by_type = defaultdict(list)
            for it in items:
                t = it.get('item_type')
                i = it.get('id')
                if t and i:
                    by_type[t].append(i)
            if not by_type:
                return set()
            ored = ['|'] * (len(by_type) - 1)
            for t, ids in by_type.items():
                ored += ['&', ('item_type', '=', t), ('item_id', 'in', ids)]
            domain = [('user_id', '=', user_id)] + ored
        recs = self.search(domain)
        return {(r.item_type, r.item_id) for r in recs}

    # ── Maintenance ──────────────────────────────────────────────────────────

    @api.model
    def cron_cleanup_old_markers(self):
        """Purge markers older than _RETENTION_DAYS to keep the table bounded."""
        cutoff = fields.Datetime.now() - timedelta(days=_RETENTION_DAYS)
        old = self.search([('read_at', '<', cutoff)])
        n = len(old)
        if n:
            _logger.info('social_feed: cleaning up %d old read marker(s)', n)
            old.unlink()
        return n
