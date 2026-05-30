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
        if 'social_pwa.push_service' not in self.env:
            return records
        # Coalesce: one push per user, even if the create() batched several
        # notifications for the same recipient.
        Service = self.env['social_pwa.push_service']
        for user_id in set(records.mapped('user_id').ids):
            try:
                Service.send_to_user(user_id)
            except Exception:
                # Push delivery is best-effort — never block the in-app
                # notification's create() on a transport failure.
                _logger.exception('social_pwa: push delivery failed for user %s', user_id)
        return records
