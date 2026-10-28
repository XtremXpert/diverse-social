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
    # The venue as a contact (tagged SAFE ZONE) — single source for name and address.
    partner_id = fields.Many2one('res.partner', "Contact lié", ondelete='set null')
    active = fields.Boolean(default=True)
    cell_lat = fields.Float(digits=(9, 6), required=True)
    cell_lon = fields.Float(digits=(9, 6), required=True)

    @api.model
    def _api_list(self):
        """Active safe zones visible to every member."""
        return [
            {'id': z.id, 'name': z.partner_id.name or z.name,
             'address': z.partner_id.contact_address_complete or z.address
                        if z.partner_id else z.address,
             'spot': {'latitude': z.cell_lat, 'longitude': z.cell_lon}}
            for z in self.sudo().search([('active', '=', True)])
        ]
