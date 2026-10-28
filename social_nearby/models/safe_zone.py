from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from .position import snap


class SocialNearbySafeZone(models.Model):
    """A named safe meeting place tied to a physical address (club, munch venue, partner
    space). Position kept snapped to its 550 m cell."""

    _name = 'social_nearby.safe_zone'
    _description = 'Safe Zone (lieu de rencontre sécuritaire)'
    _order = 'name'

    name = fields.Char(required=True)
    address = fields.Char("Adresse")
    active = fields.Boolean(default=True)
    cell_lat = fields.Float(digits=(9, 6), required=True)
    cell_lon = fields.Float(digits=(9, 6), required=True)

    @api.model
    def _api_list(self):
        """Active safe zones visible to every member."""
        return [
            {'id': z.id, 'name': z.name, 'address': z.address,
             'spot': {'latitude': z.cell_lat, 'longitude': z.cell_lon}}
            for z in self.sudo().search([('active', '=', True)])
        ]
