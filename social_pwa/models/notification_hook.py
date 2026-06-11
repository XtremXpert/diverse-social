import logging

from odoo import api, models

_logger = logging.getLogger(__name__)


class ClubSocialNotification(models.Model):
    """Fan out every new in-app notification to the user's PWA subscriptions.

    The PWA payload is generic (constant title + body) — no actor name,
    no notification type, no message preview. The user only learns which
    notification it was after tapping into the app.
    """
    _inherit = 'club_social_profile.notification'

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        Outbox = self.env.get('social_pwa.push_outbox')
        if Outbox is None:
            return records
        # Decoupled delivery: enqueue one pending row per recipient (no network
        # I/O in this transaction) and nudge the dispatch cron to run right
        # after commit. The cron coalesces and delivers with retries — so a
        # slow or failing push transport never blocks notification.create().
        user_ids = set(records.mapped('user_id').ids)
        if not user_ids:
            return records
        self.env['social_pwa.push_outbox'].enqueue(user_ids)
        cron = self.env.ref('social_pwa.cron_push_dispatch', raise_if_not_found=False)
        if cron:
            cron.sudo()._trigger()
        return records
