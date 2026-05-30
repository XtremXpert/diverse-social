from odoo import fields, models


class ClubSocialLanguage(models.Model):
    _name = 'club_social_profile.language'
    _description = 'Spoken Language'
    _order = 'sequence, name'

    name = fields.Char(required=True)
    sequence = fields.Integer(default=10)
