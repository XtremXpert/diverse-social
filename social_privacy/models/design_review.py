from odoo import models, fields, api, _


class PrivacyDesignReview(models.Model):
    _name = 'social_privacy.design.review'
    _description = 'Privacy by Design Review'
    _order = 'create_date desc'
    _inherit = ['mail.thread']

    name = fields.Char(string='Feature Name', required=True)
    description = fields.Text(string='Feature Description')

    # Data assessment
    data_collected = fields.Text(
        string='Personal Data Collected',
        help='List all personal data categories this feature collects.',
    )
    is_sensitive = fields.Boolean(
        string='Sensitive Data',
        help='Does this feature process data considered sensitive under Loi 25?',
    )
    legal_basis = fields.Selection([
        ('consent', 'Consent'),
        ('contract', 'Contract'),
        ('legal_obligation', 'Legal Obligation'),
        ('legitimate_interest', 'Legitimate Interest'),
        ('vital_interests', 'Vital Interests'),
    ], string='Legal Basis', required=True)

    # Retention
    retention_duration = fields.Char(
        string='Planned Retention Duration',
        help='e.g. 2 years, until account deletion',
    )
    retention_rule_id = fields.Many2one(
        'social_privacy.retention.rule',
        string='Linked Retention Rule',
    )

    # Risk
    risk_level = fields.Selection([
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
    ], string='Privacy Risk Level', required=True, default='low')
    risk_mitigation = fields.Text(string='Risk Mitigation Measures')

    # Review workflow
    state = fields.Selection([
        ('draft', 'Draft'),
        ('review', 'Under Review'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ], string='Status', default='draft', required=True, tracking=True)

    dpo_id = fields.Many2one('social_privacy.officer', string='DPO Reviewer')
    dpo_review_date = fields.Date(string='DPO Review Date')
    dpo_comments = fields.Text(string='DPO Comments')

    def action_submit_review(self):
        self.write({'state': 'review'})

    def action_approve(self):
        self.ensure_one()
        if not self.dpo_id:
            raise ValueError(_('A DPO reviewer must be assigned before approval.'))
        self.write({
            'state': 'approved',
            'dpo_review_date': fields.Date.today(),
        })

    def action_reject(self):
        self.write({'state': 'rejected'})
