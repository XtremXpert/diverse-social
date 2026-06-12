import logging

from odoo import api, models

_logger = logging.getLogger(__name__)


class ClubSocialNotification(models.Model):
    """Fan out every new in-app notification to the user's push devices.

    The push payload is generic (constant title + body) — no actor name,
    no notification type, no message preview. The user only learns which
    notification it was after tapping into the app.
    """
    _inherit = 'club_social_profile.notification'

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        if 'social_pwa.push_service' not in self.env:
            return records
        user_ids = list(set(records.mapped('user_id').ids))
        if user_ids:
            try:
                self.env['social_pwa.push_service'].enqueue_for_users(user_ids)
            except Exception:
                # Push delivery is best-effort — never block the in-app
                # notification's create() on a queueing failure.
                _logger.exception('social_pwa: push enqueue failed for users %s', user_ids)
        return records
