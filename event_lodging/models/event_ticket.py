from odoo import fields, models


class EventTicket(models.Model):
    _inherit = 'event.event.ticket'

    lodging_type = fields.Selection([
        ('none', 'Sans hébergement'),
        ('single', 'Lit simple'),
        ('double', 'Lit double (couple)'),
    ], string="Type d'hébergement", default='none', required=True)
