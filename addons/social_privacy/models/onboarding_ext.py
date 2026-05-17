from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class SocialOnboardingWizard(models.TransientModel):
    _inherit = 'social_onboarding.wizard'

    # Privacy consent field added to the onboarding flow
    privacy_policy_accepted = fields.Boolean(
        string='I have read and accept the privacy policy',
        default=False,
    )
    privacy_policy_version = fields.Char(
        string='Privacy Policy Version',
        readonly=True,
    )

    @api.model
    def action_open(self):
        res = super().action_open()
        # Load current privacy policy version into wizard if not set
        wizard = self.browse(res.get('res_id', False)) if isinstance(res, dict) and res.get('type') == 'ir.actions.act_window' else self
        if wizard:
            wizard.privacy_policy_version = self._get_current_privacy_version()
        return res

    @api.model
    def _get_current_privacy_version(self):
        # Load from the active policy version model
        policy = self.env['social_privacy.policy.version'].get_current_for_user()
        return policy.version_number if policy else '1.0'

    def action_finish(self):
        self.ensure_one()
        # Validate privacy consent before finishing onboarding
        if not self.privacy_policy_accepted:
            raise ValidationError(_(
                'You must accept the privacy policy before completing your profile.'
            ))
        # Record formal consent
        policy = self.env['social_privacy.policy.version'].get_current_for_user()
        if policy:
            self.env['social_privacy.consent'].sudo().record_consent(
                user=self.env.user,
                policy_version=policy,
                ip_address=self.env.context.get('client_ip'),
                source='onboarding',
            )
        # Also keep an access log for audit trail
        self.env['social_privacy.access_log'].sudo().create({
            'user_id': self.env.user.id,
            'target_user_id': self.env.user.id,
            'model_name': 'social_onboarding.wizard',
            'record_id': self.id,
            'action': 'write',
            'reason': 'Privacy policy accepted during onboarding (v%s)' % self.privacy_policy_version,
        })
        return super().action_finish()
