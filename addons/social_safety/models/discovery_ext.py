from odoo import models


class DiscoveryCriteria(models.Model):
    """Exclude blocked profiles and panic-mode profiles from discovery results."""
    _inherit = 'social_discovery.criteria'

    def _find_profiles(self):
        profiles = super()._find_profiles()
        searcher_user = self.profile_id.user_id

        # Exclude both-direction blocks
        blocked_ids = self.env['social_safety.block'].get_blocked_ids_for(searcher_user)
        if blocked_ids:
            profiles = profiles.filtered(lambda p: p.user_id.id not in blocked_ids)

        # Exclude profiles in panic mode (unless we're a connection)
        profiles = profiles.filtered(
            lambda p: not p.panic_mode or
            self.env['club_social_profile.connection'].is_connected(p.user_id, searcher_user)
        )

        return profiles
