from odoo import api, fields, models
from odoo.exceptions import ValidationError


class EventRegistration(models.Model):
    _inherit = 'event.registration'

    lodging_type = fields.Selection(
        related='event_ticket_id.lodging_type',
        string="Type d'hébergement",
        store=True,
        readonly=True,
    )
    partner2_id = fields.Many2one(
        'res.partner',
        string="Partenaire 2 (couple)",
        help="Second participant du forfait couple.",
    )

    @api.constrains('lodging_type', 'partner2_id')
    def _check_partner2_required(self):
        for reg in self:
            if reg.lodging_type == 'double' and not reg.partner2_id:
                raise ValidationError(
                    "Le partenaire 2 est obligatoire pour un forfait couple."
                )

    @api.constrains('partner_id', 'partner2_id')
    def _check_partner2_different(self):
        for reg in self:
            if reg.partner2_id and reg.partner_id and reg.partner2_id == reg.partner_id:
                raise ValidationError(
                    "Le partenaire 2 doit être différent du participant principal."
                )
