from odoo import fields, models


class ClubSocialNotification(models.Model):
    """Ajoute le type de notification 'missed_call' (appel manqué)."""
    _inherit = 'club_social_profile.notification'

    type = fields.Selection(
        selection_add=[('missed_call', 'Missed Call')],
        ondelete={'missed_call': 'cascade'},
    )
