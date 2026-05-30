from odoo import models


class ClubSocialProfileOnboarding(models.Model):
    _inherit = 'club_social_profile.profile'

    def action_open_onboarding(self):
        """Redirect to the public portal onboarding flow.

        The backend wizard still exists (used by tests and some admin
        actions), but the "Complete my profile" button on the profile
        banner must send the member to ``/onboarding`` — the multi-step
        public flow — rather than to the single-page backend form.
        """
        return {
            'type': 'ir.actions.act_url',
            'url': '/onboarding',
            'target': 'self',
        }
