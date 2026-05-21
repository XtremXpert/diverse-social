import datetime

from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


@tagged('social_onboarding', 'onboarding')
class TestSocialOnboarding(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        group_social = cls.env.ref('social_base.group_social_user')

        cls.user = cls.env['res.users'].create({
            'name': 'Onboarding User',
            'login': 'onb_user',
            'email': 'onb@test.test',
            'group_ids': [(4, group_social.id)],
        })
        cls.type_regular = cls.env.ref('club_membership.membership_type_regular')

    # ── Wizard creation ───────────────────────────────────────────────────────

    def test_action_open_creates_wizard(self):
        """action_open creates a wizard record and returns an open action."""
        action = self.env['social_onboarding.wizard'].with_user(self.user).action_open()
        self.assertEqual(action['type'], 'ir.actions.act_window')
        self.assertEqual(action['res_model'], 'social_onboarding.wizard')
        self.assertIsNotNone(action['res_id'])

    def test_action_open_creates_profile(self):
        """action_open creates the profile if it does not exist."""
        before = self.env['club_social_profile.profile'].search_count(
            [('user_id', '=', self.user.id)]
        )
        self.env['social_onboarding.wizard'].with_user(self.user).action_open()
        after = self.env['club_social_profile.profile'].search_count(
            [('user_id', '=', self.user.id)]
        )
        self.assertEqual(after, before + 1)

    def test_action_open_reuses_existing_profile(self):
        """action_open does not create a duplicate if the profile already exists."""
        profile = self.env['club_social_profile.profile'].sudo().get_or_create_for_user(self.user)
        self.env['social_onboarding.wizard'].with_user(self.user).action_open()
        count = self.env['club_social_profile.profile'].search_count(
            [('user_id', '=', self.user.id)]
        )
        self.assertEqual(count, 1)

    def test_wizard_starts_at_welcome_step(self):
        """The wizard starts on step 'welcome' for an incomplete profile."""
        action = self.env['social_onboarding.wizard'].with_user(self.user).action_open()
        wizard = self.env['social_onboarding.wizard'].browse(action['res_id'])
        self.assertEqual(wizard.step, 'welcome')

    # ── Navigation ────────────────────────────────────────────────────────────

    def test_action_next_advances_step(self):
        """action_next moves to the next step."""
        action = self.env['social_onboarding.wizard'].with_user(self.user).action_open()
        wizard = self.env['social_onboarding.wizard'].browse(action['res_id'])
        self.assertEqual(wizard.step, 'welcome')
        wizard.action_next()
        self.assertEqual(wizard.step, 'about')

    def test_action_next_all_steps(self):
        """action_next walks through every step in order."""
        action = self.env['social_onboarding.wizard'].with_user(self.user).action_open()
        wizard = self.env['social_onboarding.wizard'].browse(action['res_id'])
        expected = ['welcome', 'about', 'preferences', 'done']
        for i, step in enumerate(expected):
            self.assertEqual(wizard.step, step)
            if i < len(expected) - 1:
                wizard.action_next()

    def test_action_previous_goes_back(self):
        """action_previous moves back to the previous step."""
        action = self.env['social_onboarding.wizard'].with_user(self.user).action_open()
        wizard = self.env['social_onboarding.wizard'].browse(action['res_id'])
        wizard.action_next()  # welcome → about
        wizard.action_next()  # about → preferences
        self.assertEqual(wizard.step, 'preferences')
        wizard.action_previous()
        self.assertEqual(wizard.step, 'about')

    def test_action_previous_does_not_go_before_welcome(self):
        """action_previous never goes below the 'welcome' step."""
        action = self.env['social_onboarding.wizard'].with_user(self.user).action_open()
        wizard = self.env['social_onboarding.wizard'].browse(action['res_id'])
        self.assertEqual(wizard.step, 'welcome')
        wizard.action_previous()
        self.assertEqual(wizard.step, 'welcome')

    def test_action_next_returns_act_window(self):
        """action_next returns an act_window pointing at the same wizard."""
        action = self.env['social_onboarding.wizard'].with_user(self.user).action_open()
        wizard = self.env['social_onboarding.wizard'].browse(action['res_id'])
        result = wizard.action_next()
        self.assertEqual(result['type'], 'ir.actions.act_window')
        self.assertEqual(result['res_id'], wizard.id)

    # ── Sauvegarde et profil ──────────────────────────────────────────────────

    def test_next_saves_photo_to_profile(self):
        """action_next sauvegarde l'image vers le profil."""
        action = self.env['social_onboarding.wizard'].with_user(self.user).action_open()
        wizard = self.env['social_onboarding.wizard'].browse(action['res_id'])
        # Simuler l'upload d'une image (1x1 pixel PNG en base64)
        fake_image = b'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=='
        wizard.write({'profile_image': fake_image})
        wizard.action_next()
        self.assertIsNotNone(wizard.profile_id.profile_image)

    def test_finish_saves_all_fields(self):
        """action_finish sauvegarde tous les champs du profil."""
        action = self.env['social_onboarding.wizard'].with_user(self.user).action_open()
        wizard = self.env['social_onboarding.wizard'].browse(action['res_id'])
        wizard.write({
            'pronouns': 'iel/iel',
            'bio': 'Biographie test',
            'birth_year': 1990,
            'city': 'Montréal',
            'visibility': 'connections',
            'availability': 'disponible',
            'digest_email_enabled': False,
        })
        # Walk forward to the preferences step so that finish() is reachable
        wizard.step = 'preferences'
        wizard.action_finish()
        profile = wizard.profile_id
        self.assertEqual(profile.pronouns, 'iel/iel')
        self.assertEqual(profile.bio, 'Biographie test')
        self.assertEqual(profile.birth_year, 1990)
        self.assertEqual(profile.city, 'Montréal')
        self.assertEqual(profile.visibility, 'connections')
        self.assertEqual(profile.availability, 'disponible')
        self.assertFalse(profile.digest_email_enabled)

    def test_finish_marks_onboarding_done(self):
        """action_finish sets onboarding_done to True."""
        action = self.env['social_onboarding.wizard'].with_user(self.user).action_open()
        wizard = self.env['social_onboarding.wizard'].browse(action['res_id'])
        self.assertFalse(wizard.profile_id.onboarding_done)
        wizard.step = 'preferences'
        wizard.action_finish()
        self.assertTrue(wizard.profile_id.onboarding_done)

    def test_skip_does_not_mark_done(self):
        """action_skip leaves onboarding_done as False."""
        action = self.env['social_onboarding.wizard'].with_user(self.user).action_open()
        wizard = self.env['social_onboarding.wizard'].browse(action['res_id'])
        wizard.action_skip()
        self.assertFalse(wizard.profile_id.onboarding_done)

    # ── Validation ────────────────────────────────────────────────────────────

    def test_underage_birth_year_blocked(self):
        """A birth year yielding less than 18 is rejected on the 'about' step."""
        action = self.env['social_onboarding.wizard'].with_user(self.user).action_open()
        wizard = self.env['social_onboarding.wizard'].browse(action['res_id'])
        current_year = datetime.date.today().year
        wizard.write({
            'step': 'about',
            'birth_year': current_year - 15,
        })
        with self.assertRaises(ValidationError):
            wizard.action_next()

    def test_valid_adult_birth_year_passes(self):
        """An adult birth year (18+) passes validation."""
        action = self.env['social_onboarding.wizard'].with_user(self.user).action_open()
        wizard = self.env['social_onboarding.wizard'].browse(action['res_id'])
        current_year = datetime.date.today().year
        wizard.write({
            'step': 'about',
            'birth_year': current_year - 25,
        })
        wizard.action_next()  # Ne doit pas lever d'exception
        self.assertEqual(wizard.step, 'preferences')

    def test_zero_birth_year_skips_validation(self):
        """A birth_year of 0 (not provided) does not trigger age validation."""
        action = self.env['social_onboarding.wizard'].with_user(self.user).action_open()
        wizard = self.env['social_onboarding.wizard'].browse(action['res_id'])
        wizard.write({'step': 'about', 'birth_year': 0})
        wizard.action_next()
        self.assertEqual(wizard.step, 'preferences')

    # ── Membership hook ───────────────────────────────────────────────────────

    def test_membership_activate_creates_profile(self):
        """Activating a membership automatically creates the member profile."""
        user2 = self.env['res.users'].create({
            'name': 'Hook Test User',
            'login': 'hook_test_onb',
            'email': 'hook@onb.test',
        })
        membership = self.env['club_membership.membership'].sudo().create({
            'partner_id': user2.partner_id.id,
            'membership_type_id': self.type_regular.id,
            'start_date': datetime.date.today(),
            'state': 'pending',
        })
        membership.action_activate()
        profile = self.env['club_social_profile.profile'].search(
            [('user_id', '=', user2.id)]
        )
        self.assertEqual(len(profile), 1)
        self.assertFalse(profile.onboarding_done)

    def test_membership_activate_no_profile_if_no_user(self):
        """Activation without an associated user does not create an orphan profile."""
        partner = self.env['res.partner'].create({'name': 'Partner without account'})
        membership = self.env['club_membership.membership'].sudo().create({
            'partner_id': partner.id,
            'membership_type_id': self.type_regular.id,
            'start_date': datetime.date.today(),
            'state': 'pending',
        })
        membership.action_activate()
        count = self.env['club_social_profile.profile'].search_count([
            ('partner_id', '=', partner.id),
        ])
        self.assertEqual(count, 0)

    # ── profile_ext method ────────────────────────────────────────────────────

    def test_profile_action_open_onboarding(self):
        """The "Complete my profile" button redirects to the portal flow."""
        profile = self.env['club_social_profile.profile'].sudo().get_or_create_for_user(self.user)
        action = profile.with_user(self.user).action_open_onboarding()
        self.assertEqual(action['type'], 'ir.actions.act_url')
        self.assertEqual(action['url'], '/onboarding')

    def test_action_open_loads_profile_data(self):
        """action_open pre-fills the wizard with the profile's existing data."""
        profile = self.env['club_social_profile.profile'].sudo().get_or_create_for_user(self.user)
        profile.sudo().write({'bio': 'Existing bio', 'city': 'Québec', 'birth_year': 1985})
        action = self.env['social_onboarding.wizard'].with_user(self.user).action_open()
        wizard = self.env['social_onboarding.wizard'].browse(action['res_id'])
        self.assertEqual(wizard.bio, 'Existing bio')
        self.assertEqual(wizard.city, 'Québec')
        self.assertEqual(wizard.birth_year, 1985)

    def test_skip_saves_to_profile(self):
        """action_skip saves the filled fields to the profile."""
        action = self.env['social_onboarding.wizard'].with_user(self.user).action_open()
        wizard = self.env['social_onboarding.wizard'].browse(action['res_id'])
        wizard.write({'bio': 'Bio via skip', 'city': 'Laval'})
        wizard.action_skip()
        profile = wizard.profile_id
        self.assertEqual(profile.bio, 'Bio via skip')
        self.assertEqual(profile.city, 'Laval')

    def test_action_next_at_done_stays_done(self):
        """action_next on step 'done' does not go past 'done'."""
        action = self.env['social_onboarding.wizard'].with_user(self.user).action_open()
        wizard = self.env['social_onboarding.wizard'].browse(action['res_id'])
        wizard.step = 'done'
        wizard.action_next()
        self.assertEqual(wizard.step, 'done')

    def test_finish_returns_client_action(self):
        """action_finish returns a client action (notification)."""
        action = self.env['social_onboarding.wizard'].with_user(self.user).action_open()
        wizard = self.env['social_onboarding.wizard'].browse(action['res_id'])
        wizard.step = 'preferences'
        result = wizard.action_finish()
        self.assertEqual(result['type'], 'ir.actions.client')
        self.assertEqual(result['tag'], 'display_notification')
