import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 5


class NtfyPushOutbox(models.Model):
    """Decoupled ntfy delivery queue.

    Same decoupling as social_pwa.push_outbox: a new in-app notification
    ENQUEUES a pending row (cheap, no network I/O in the originating
    transaction); a frequent cron coalesces pending rows per user and POSTs
    once each to ntfy, with bounded retries. Delivered rows are deleted, so the
    table only ever holds pending or permanently-failed rows.
    """
    _name = 'social_ntfy.push_outbox'
    _description = 'Pending ntfy Push Delivery'
    _order = 'id'

    user_id = fields.Many2one('res.users', required=True, ondelete='cascade', index=True)
    state = fields.Selection(
        [('pending', 'Pending'), ('failed', 'Failed')],
        default='pending', required=True, index=True,
    )
    attempts = fields.Integer(default=0)
    last_error = fields.Char()

    @api.model
    def enqueue(self, user_ids):
        """One pending row per recipient that actually has a ntfy topic.
        Skipping topic-less users keeps the outbox (and cron) idle until a
        member opts in by visiting their profile settings."""
        Profile = self.env['club_social_profile.profile'].sudo()
        targets = [
            uid for uid in set(user_ids)
            if uid and Profile.search_count(
                [('user_id', '=', uid), ('ntfy_topic', '!=', False)])
        ]
        if targets:
            self.sudo().create([{'user_id': uid} for uid in targets])

    @api.model
    def _cron_dispatch(self, batch=300):
        """Coalesce pending pushes per user and deliver them, with bounded
        retries. Commits per user so one user's failure never rolls back
        another user's successful delivery."""
        pending = self.sudo().search([('state', '=', 'pending')], limit=batch)
        if not pending:
            return
        Service = self.env['social_ntfy.push_service'].sudo()
        by_user = {}
        for row in pending:
            by_user.setdefault(row.user_id.id, self.browse())
            by_user[row.user_id.id] |= row
        for user_id, rows in by_user.items():
            try:
                Service.send_to_user(user_id)
                rows.unlink()  # delivered (or dropped 4xx) → drop from the queue
            except Exception as exc:  # transient/unexpected → retry until cap
                _logger.warning(
                    'social_ntfy: push dispatch failed for user %s: %s', user_id, exc)
                for row in rows:
                    attempts = row.attempts + 1
                    row.write({
                        'attempts': attempts,
                        'last_error': str(exc)[:200],
                        'state': 'failed' if attempts >= MAX_ATTEMPTS else 'pending',
                    })
            self.env.cr.commit()
