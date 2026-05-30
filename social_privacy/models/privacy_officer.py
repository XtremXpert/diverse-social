from odoo import models, fields


class PrivacyOfficer(models.Model):
    _name = 'social_privacy.officer'
    _description = 'Privacy Officer (DPO)'
    _order = 'appointment_date desc'

    user_id = fields.Many2one('res.users', string='Officer', required=True)
    company_id = fields.Many2one('res.company', string='Company',
                                 default=lambda s: s.env.company)
    appointment_date = fields.Date(string='Appointment Date',
                                   default=fields.Date.today)
    contact_email = fields.Char(string='Email', related='user_id.email',
                                store=True)
    contact_phone = fields.Char(string='Phone')
    is_active = fields.Boolean(string='Active', default=True)
    notes = fields.Text(string='Notes')
