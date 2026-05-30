from odoo import api, fields, models


class EventRegistration(models.Model):
    _inherit = 'event.registration'

    user_id = fields.Many2one(
        'res.users',
        string='Membre',
        domain=[('share', '=', False), ('active', '=', True)],
        index='btree_not_null',
    )

    @api.onchange('user_id')
    def _onchange_user_id(self):
        if self.user_id:
            self.partner_id = self.user_id.partner_id
            self.name = self.user_id.login
            self.email = self.user_id.email

    def _get_website_registration_allowed_fields(self):
        return super()._get_website_registration_allowed_fields() | {'user_id'}
