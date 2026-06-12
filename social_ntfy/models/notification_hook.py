import logging

from odoo import api, models

_logger = logging.getLogger(__name__)


class ClubSocialNotification(models.Model):
    """Fan out every new in-app notification to the user's ntfy topic.

    The ntfy payload is generic (constant title + body) — no actor name, no
    notification type, no message preview. Independent of social_pwa: if both
    are installed, a notification triggers both a web-push and a ntfy push.
    """
    _inherit = 'club_social_profile.notification'

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        Outbox = self.env.get('social_ntfy.push_outbox')
        if Outbox is None:
            return records
        # Decoupled delivery: enqueue one pending row per recipient (no network
        # I/O here) and nudge the dispatch cron so the push goes out within
        # seconds without blocking notification.create().
        user_ids = set(records.mapped('user_id').ids)
        if not user_ids:
            return records
        self.env['social_ntfy.push_outbox'].enqueue(user_ids)
        cron = self.env.ref('social_ntfy.cron_ntfy_dispatch', raise_if_not_found=False)
        if cron:
            cron.sudo()._trigger()
        return records
