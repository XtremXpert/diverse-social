from odoo import fields, models


class ClubSocialNotification(models.Model):
    _inherit = 'club_social_profile.notification'

    type = fields.Selection(
        selection_add=[
            ('residency_pending', 'Residency Submitted'),
            ('residency_verified', 'Residency Approved'),
            ('residency_rejected', 'Residency Rejected'),
        ],
        ondelete={
            'residency_pending': 'cascade',
            'residency_verified': 'cascade',
            'residency_rejected': 'cascade',
        },
    )
