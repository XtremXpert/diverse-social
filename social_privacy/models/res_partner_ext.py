from odoo import models, fields


class ResPartner(models.Model):
    _inherit = 'res.partner'

    is_anonymized = fields.Boolean(
        string='Anonymized',
        default=False,
        help='Set to True when the partner has been anonymized via privacy_partner_to_be_forgotten.',
    )
    anonymization_date = fields.Datetime(string='Anonymization Date')
