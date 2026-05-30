from odoo import fields, models


class EventEventTicket(models.Model):
    _inherit = 'event.event.ticket'

    require_member_name = fields.Boolean(
        string='Capturer le membre',
        help="Si coché, le formulaire d'inscription demande de sélectionner un membre (res.users) pour ce type de billet.",
    )
