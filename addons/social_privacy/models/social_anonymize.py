from odoo import models, fields, api, _


# --- Model to track anonymization jobs (for audit trail) ---

class SocialAnonymizeLog(models.Model):
    _name = 'social_privacy.anonymize_log'
    _description = 'Social Anonymization Log'
    _order = 'create_date desc'

    partner_id = fields.Many2one('res.partner', string='Partner', required=True, ondelete='restrict')
    user_id = fields.Many2one('res.users', string='User', required=True, ondelete='restrict')
    triggered_by_id = fields.Many2one('res.users', string='Triggered By', default=lambda s: s.env.user)
    status = fields.Selection([
        ('pending', 'Pending'),
        ('done', 'Done'),
        ('failed', 'Failed'),
    ], default='pending', required=True)
    details = fields.Text(string='Details')

    def action_log_anonymization(self, partner, user, status, details):
        return self.create({
            'partner_id': partner.id,
            'user_id': user.id,
            'status': status,
            'details': details,
        })
