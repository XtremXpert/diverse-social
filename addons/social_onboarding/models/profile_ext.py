from odoo import models


class ClubSocialProfileOnboarding(models.Model):
    _inherit = 'club_social_profile.profile'

    def action_open_onboarding(self):
        """Redirige vers le parcours d'intégration côté portail public.

        Le wizard backend existe toujours (utilisé par les tests et certaines
        actions admin), mais le bouton "Compléter mon profil" sur la bannière
        de la fiche profil doit envoyer le membre vers `/onboarding`
        (interface front, multi-étapes complète) plutôt que vers la vue
        formulaire backend mono-étape.
        """
        return {
            'type': 'ir.actions.act_url',
            'url': '/onboarding',
            'target': 'self',
        }
