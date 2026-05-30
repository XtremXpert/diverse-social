from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class PrivacyPolicyVersion(models.Model):
    _name = 'social_privacy.policy.version'
    _description = 'Privacy Policy Version'
    _order = 'effective_date desc'

    name = fields.Char(string='Version Name', required=True)
    version_number = fields.Char(string='Version Number', required=True)
    effective_date = fields.Date(string='Effective Date', required=True, default=fields.Date.today)
    content = fields.Html(string='Policy Text', required=True,
                          help='Full text of the privacy policy as presented to users.')
    is_active = fields.Boolean(string='Active', default=True)
    language = fields.Selection([
        ('en', 'English'),
        ('fr', 'French'),
    ], string='Language', default='fr', required=True)

    # Computed
    consent_count = fields.Integer(string='Consents Given', compute='_compute_consent_count')

    @api.depends('consent_ids')
    def _compute_consent_count(self):
        for policy in self:
            policy.consent_count = len(policy.consent_ids)

    consent_ids = fields.One2many('social_privacy.consent', 'policy_version_id', string='Consents')

    @api.constrains('effective_date', 'is_active')
    def _check_unique_active_version(self):
        for policy in self:
            if policy.is_active:
                dup = self.search([
                    ('id', '!=', policy.id),
                    ('language', '=', policy.language),
                    ('is_active', '=', True),
                ], limit=1)
                if dup:
                    raise ValidationError(_(
                        'Only one active privacy policy per language is allowed. '
                        'Please deactivate version %(other)s first.',
                        other=dup.name,
                    ))

    def action_set_active(self):
        self.ensure_one()
        # Deactivate others in same language
        self.search([
            ('id', '!=', self.id),
            ('language', '=', self.language),
            ('is_active', '=', True),
        ]).write({'is_active': False})
        self.write({'is_active': True})

    @api.model
    def get_current_for_user(self, user=None):
        """Return the active policy version for the user's language."""
        lang = 'fr'  # Default; could be derived from user.partner_id.lang
        return self.search([
            ('language', '=', lang),
            ('is_active', '=', True),
        ], limit=1, order='effective_date desc')
