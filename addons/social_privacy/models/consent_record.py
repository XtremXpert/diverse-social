from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class PrivacyConsent(models.Model):
    _name = 'social_privacy.consent'
    _description = 'Privacy Consent Record'
    _order = 'consented_at desc'
    _rec_name = 'user_id'

    user_id = fields.Many2one('res.users', string='User', required=True, ondelete='restrict', index=True)
    policy_version_id = fields.Many2one(
        'social_privacy.policy.version',
        string='Policy Version',
        required=True,
        ondelete='restrict',
    )
    policy_version_number = fields.Char(
        string='Version Number',
        related='policy_version_id.version_number',
        store=True,
    )

    # Consent state
    state = fields.Selection([
        ('accepted', 'Accepted'),
        ('withdrawn', 'Withdrawn'),
    ], string='Status', default='accepted', required=True)

    # Audit trail
    consented_at = fields.Datetime(string='Consented At', required=True, default=fields.Datetime.now)
    withdrawn_at = fields.Datetime(string='Withdrawn At')
    ip_address = fields.Char(string='IP Address')
    user_agent = fields.Char(string='User Agent')

    # Context
    source = fields.Selection([
        ('onboarding', 'Onboarding'),
        ('portal', 'Portal Privacy Page'),
        ('admin', 'Administrator Action'),
        ('api', 'API / Mobile'),
    ], string='Source', default='onboarding', required=True)

    # Withdrawal reason
    withdrawal_reason = fields.Text(string='Withdrawal Reason')

    _unique_active_consent = models.Constraint(
        'unique(user_id, policy_version_id)',
        'A consent record already exists for this user and policy version.',
    )

    def action_withdraw(self, reason=''):
        self.ensure_one()
        if self.state == 'withdrawn':
            raise ValidationError(_('Consent is already withdrawn.'))
        self.write({
            'state': 'withdrawn',
            'withdrawn_at': fields.Datetime.now(),
            'withdrawal_reason': reason or False,
        })
        # Log the withdrawal
        self.env['social_privacy.access_log'].sudo().create({
            'user_id': self.env.user.id,
            'target_user_id': self.user_id.id,
            'model_name': self._name,
            'record_id': self.id,
            'action': 'write',
            'reason': 'Consent withdrawn: %s' % (reason or 'No reason provided'),
        })

    @api.model
    def record_consent(self, user, policy_version, ip_address=None, user_agent=None, source='onboarding'):
        """Create or update a consent record for a user."""
        existing = self.search([
            ('user_id', '=', user.id),
            ('policy_version_id', '=', policy_version.id),
        ], limit=1)
        if existing:
            # Reactivate if previously withdrawn
            if existing.state == 'withdrawn':
                existing.write({
                    'state': 'accepted',
                    'consented_at': fields.Datetime.now(),
                    'ip_address': ip_address,
                    'user_agent': user_agent,
                    'source': source,
                    'withdrawn_at': False,
                    'withdrawal_reason': False,
                })
            return existing
        return self.create({
            'user_id': user.id,
            'policy_version_id': policy_version.id,
            'ip_address': ip_address,
            'user_agent': user_agent,
            'source': source,
            'consented_at': fields.Datetime.now(),
        })

    @api.model
    def has_valid_consent(self, user):
        """Check if the user has an active consent for the current policy version."""
        current_policy = self.env['social_privacy.policy.version'].get_current_for_user(user)
        if not current_policy:
            return False
        consent = self.search([
            ('user_id', '=', user.id),
            ('policy_version_id', '=', current_policy.id),
            ('state', '=', 'accepted'),
        ], limit=1)
        return bool(consent)
