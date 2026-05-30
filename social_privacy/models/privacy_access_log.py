from odoo import models, fields, api


class PrivacyAccessLog(models.Model):
    _name = 'social_privacy.access_log'
    _description = 'Privacy Access Log'
    _order = 'create_date desc'

    user_id = fields.Many2one(
        'res.users',
        string='Accessed By',
        required=True,
        default=lambda s: s.env.user,
        ondelete='restrict',
    )
    target_user_id = fields.Many2one(
        'res.users',
        string='Data Owner',
        index=True,
        ondelete='restrict',
    )
    model_name = fields.Char(string='Model', required=True)
    record_id = fields.Integer(string='Record ID', required=True)
    action = fields.Selection([
        ('read', 'Read'),
        ('write', 'Update'),
        ('delete', 'Delete'),
        ('export', 'Export'),
        ('anonymize', 'Anonymize'),
    ], string='Action', required=True)
    reason = fields.Text(string='Reason')
    ip_address = fields.Char(string='IP Address')

    @api.model_create_multi
    def create(self, vals_list):
        # Auto-capture IP if available in context
        for vals in vals_list:
            if not vals.get('ip_address') and self.env.context.get('client_ip'):
                vals['ip_address'] = self.env.context['client_ip']
        return super().create(vals_list)
