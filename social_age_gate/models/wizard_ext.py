from odoo import _, fields, models
from odoo.exceptions import ValidationError


class SocialOnboardingWizardAgeGate(models.TransientModel):
    _inherit = 'social_onboarding.wizard'

    step = fields.Selection(
        selection_add=[('age_gate', 'Age verification (18+)')],
        ondelete={'age_gate': 'set default'},
    )
    age_gate_confirmed = fields.Boolean('I confirm I am 18 or older')

    # ── Navigation ────────────────────────────────────────────────────────────

    def action_next(self):
        self.ensure_one()
        if self.step == 'about':
            self._validate_current_step()
            self._save_to_profile()
            if not self._age_gate_passed():
                self.step = 'age_gate'
                return self._build_action()
            self.step = 'preferences'
            return self._build_action()

        if self.step == 'age_gate':
            if not self.age_gate_confirmed:
                raise ValidationError(
                    _("You must confirm being 18 or older to access the social network.")
                )
            self.profile_id.sudo().write({'age_gate_passed': True})
            self._save_to_profile()
            self.step = 'preferences'
            return self._build_action()

        return super().action_next()

    def action_previous(self):
        self.ensure_one()
        if self.step == 'age_gate':
            self.step = 'about'
            return self._build_action()
        if self.step == 'preferences':
            self.step = 'about'
            return self._build_action()
        return super().action_previous()

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _age_gate_passed(self):
        return bool(self.profile_id and self.profile_id.sudo().age_gate_passed)
