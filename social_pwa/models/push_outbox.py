import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 5


class PwaPushOutbox(models.Model):
    """Decoupled web-push delivery queue.

    A new in-app notification ENQUEUES a pending row here (cheap, no network
    I/O inside the originating transaction) instead of pushing inline. A
    frequent cron then coalesces pending rows per user and calls
    push_service.send_to_user once each, with bounded retries. Benefits:

      - notification.create() stays fast and never blocks on a push transport;
      - multiple notifications for the same user in a window → a single push;
      - a transient push-service outage doesn't lose the notification — the
        row stays 'pending' and is retried on the next tick (up to MAX_ATTEMPTS).

    Delivered rows are deleted immediately, so the table only ever holds
    pending or permanently-failed rows.
    """
    _name = 'social_pwa.push_outbox'
    _description = 'Pending Web Push Delivery'
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
        """Create one pending row per recipient user that actually has at least
        one push subscription. Skipping users with no subscribed device keeps
        the outbox empty (and the cron idle) while push is off or a user hasn't
        opted in. Caller may be a portal user, so go through sudo."""
        Sub = self.env['social_pwa.subscription'].sudo()
        targets = [
            uid for uid in set(user_ids)
            if uid and Sub.search_count([('user_id', '=', uid)])
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
        Service = self.env['social_pwa.push_service'].sudo()
        by_user = {}
        for row in pending:
            by_user.setdefault(row.user_id.id, self.browse())
            by_user[row.user_id.id] |= row
        for user_id, rows in by_user.items():
            try:
                Service.send_to_user(user_id)
                rows.unlink()  # delivered → drop from the queue
            except Exception as exc:  # transient/unexpected → retry until cap
                _logger.warning(
                    'social_pwa: push dispatch failed for user %s: %s', user_id, exc)
                for row in rows:
                    attempts = row.attempts + 1
                    row.write({
                        'attempts': attempts,
                        'last_error': str(exc)[:200],
                        'state': 'failed' if attempts >= MAX_ATTEMPTS else 'pending',
                    })
            self.env.cr.commit()
