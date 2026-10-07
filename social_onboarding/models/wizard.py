from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


_STEPS = ['welcome', 'about', 'preferences', 'done']


class SocialOnboardingWizard(models.TransientModel):
    _name = 'social_onboarding.wizard'
    _description = "Social Network Onboarding Wizard"

    step = fields.Selection([
        ('welcome', 'Welcome'),
        ('about', 'About'),
        ('preferences', 'Preferences'),
        ('done', 'Done'),
    ], default='welcome', required=True)

    profile_id = fields.Many2one('club_social_profile.profile', readonly=True)

    # ── Step 1: photo ─────────────────────────────────────────────────────────
    profile_image = fields.Image(max_width=400, max_height=400, string='Profile Picture')

    # ── Step 2: about ─────────────────────────────────────────────────────────
    pronouns = fields.Char('Pronouns')
    bio = fields.Text('Bio')
    birth_year = fields.Integer("Birth Year")
    city = fields.Char('City')

    # ── Step 3: preferences ───────────────────────────────────────────────────
    visibility = fields.Selection([
        ('members', 'Club Members'),
        ('connections', 'Connections Only'),
    ], string='Profile Visibility', default='members', required=True)
    availability = fields.Selection([
        ('disponible', 'Available / Looking'),
        ('couple_ouvert', 'Open Couple'),
        ('couple_ferme', 'Closed Couple'),
        ('pas_disponible', 'Not Available'),
        ('non_specifie', 'Unspecified'),
    ], string='Availability', default='non_specifie')
    digest_email_enabled = fields.Boolean(
        'Receive the weekly digest by email', default=True,
    )

    # ── Open ──────────────────────────────────────────────────────────────────

    @api.model
    def action_open(self):
        """Create or load the wizard for the current user."""
        Profile = self.env['club_social_profile.profile']
        profile = Profile.sudo().get_or_create_for_user(self.env.user)
        wizard = self.create({
            'profile_id': profile.id,
            'profile_image': profile.profile_image,
            'pronouns': profile.pronouns or False,
            'bio': profile.bio or False,
            'birth_year': profile.birth_year or 0,
            'city': profile.city or False,
            'visibility': profile.visibility or 'members',
            'availability': profile.availability or 'non_specifie',
            'digest_email_enabled': profile.digest_email_enabled,
            'step': 'welcome' if not profile.onboarding_done else 'done',
        })
        return wizard._build_action()

    def _build_action(self):
        return {
            'type': 'ir.actions.act_window',
            'name': _("Complete my profile"),
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'views': [(False, 'form')],  # requis par Odoo 20
            'target': 'current',
        }

    # ── Navigation ────────────────────────────────────────────────────────────

    def action_next(self):
        self.ensure_one()
        self._validate_current_step()
        self._save_to_profile()
        idx = _STEPS.index(self.step)
        if idx < len(_STEPS) - 1:
            self.step = _STEPS[idx + 1]
        return self._build_action()

    def action_previous(self):
        self.ensure_one()
        idx = _STEPS.index(self.step)
        if idx > 0:
            self.step = _STEPS[idx - 1]
        return self._build_action()

    def action_finish(self):
        self.ensure_one()
        self._save_to_profile()
        self.profile_id.sudo().write({'onboarding_done': True})
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _("Welcome!"),
                'message': _("Your profile is now complete. Enjoy exploring!"),
                'type': 'success',
                'sticky': False,
                'next': {
                    'type': 'ir.actions.act_window',
                    'res_model': 'social_base.post',
                    'view_mode': 'list,form',
                    'views': [(False, 'list'), (False, 'form')],  # requis par Odoo 20
                    'target': 'current',
                },
            },
        }

    def action_skip(self):
        """Close the wizard without marking the profile as complete."""
        self.ensure_one()
        self._save_to_profile()
        return {'type': 'ir.actions.act_window_close'}

    # ── Saving and validation ────────────────────────────────────────────────

    def _validate_current_step(self):
        """Validate the current step fields before moving to the next."""
        if self.step == 'about' and self.birth_year:
            import datetime
            current_year = datetime.date.today().year
            age = current_year - self.birth_year
            if 0 < age < 18:
                raise ValidationError(
                    _("You must be 18 or older to access the social network.")
                )

    def _save_to_profile(self):
        if not self.profile_id:
            return
        self.profile_id.sudo().write({
            'profile_image': self.profile_image,
            'pronouns': self.pronouns or False,
            'bio': self.bio or False,
            'birth_year': self.birth_year or 0,
            'city': self.city or False,
            'visibility': self.visibility,
            'availability': self.availability,
            'digest_email_enabled': self.digest_email_enabled,
        })
