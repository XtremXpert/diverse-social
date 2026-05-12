from odoo import fields, models


class ClubSocialLookingFor(models.Model):
    _name = 'club_social_profile.looking_for'
    _description = 'What the Member is Looking For'
    _order = 'sequence, name'

    name = fields.Char(required=True)
    sequence = fields.Integer(default=10)
