from odoo import models


class ClubSocialProfileOnboarding(models.Model):
    _inherit = 'club_social_profile.profile'

    def action_open_onboarding(self):
        """Ouvre l'assistant d'intégration pour le profil courant."""
        return self.env['social_onboarding.wizard'].action_open()
