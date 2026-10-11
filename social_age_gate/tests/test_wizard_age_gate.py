from odoo.tests import TransactionCase, tagged
from odoo.exceptions import ValidationError


def _make_member(env, name, login, **profile_vals):
    group_user = env.ref('base.group_user')
    group_social = env.ref('social_base.group_social_user')
    user = env['res.users'].create({
        'name': name, 'login': login, 'email': f'{login}@wizard.test',
        'group_ids': [(4, group_user.id), (4, group_social.id)],
    })
    profile = env['club_social_profile.profile'].sudo().get_or_create_for_user(user)
    if profile_vals:
        profile.sudo().write(profile_vals)
    return user, profile


@tagged('social_age_gate', 'wizard_age_gate')
class TestWizardAgeGate(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user, cls.profile = _make_member(cls.env, 'WizUser', 'wiz_user')

    def _open_wizard(self, user=None):
        return self.env['social_onboarding.wizard'].with_user(
            user or self.user
        ).action_open()

    def _get_wizard(self, user=None):
        action = self._open_wizard(user)
        return self.env['social_onboarding.wizard'].browse(action['res_id'])

    def test_wizard_opens_without_error(self):
        wizard = self._get_wizard()
        self.assertIn(wizard.step, ('welcome', 'done'))

    def test_next_from_about_goes_to_age_gate_when_not_passed(self):
        self.profile.sudo().write({'age_gate_passed': False})
        wizard = self._get_wizard()
        wizard.step = 'about'
        wizard.action_next()
        self.assertEqual(wizard.step, 'age_gate')

    def test_next_from_about_skips_age_gate_when_passed(self):
        self.profile.sudo().write({'age_gate_passed': True})
        wizard = self._get_wizard()
        wizard.step = 'about'
        wizard.action_next()
        self.assertEqual(wizard.step, 'preferences')

    def test_next_from_age_gate_without_confirmation_raises(self):
        self.profile.sudo().write({'age_gate_passed': False})
        wizard = self._get_wizard()
        wizard.step = 'age_gate'
        wizard.age_gate_confirmed = False
        with self.assertRaises(ValidationError):
            wizard.action_next()

    def test_next_from_age_gate_with_confirmation_sets_passed(self):
        user2, profile2 = _make_member(self.env, 'WizUser2', 'wiz_user2', age_gate_passed=False)
        wizard = self._get_wizard(user=user2)
        wizard.step = 'age_gate'
        wizard.age_gate_confirmed = True
        wizard.action_next()
        self.assertEqual(wizard.step, 'preferences')
        self.assertTrue(profile2.sudo().age_gate_passed)

    def test_previous_from_age_gate_goes_to_about(self):
        wizard = self._get_wizard()
        wizard.step = 'age_gate'
        wizard.action_previous()
        self.assertEqual(wizard.step, 'about')

    def test_previous_from_preferences_goes_to_about(self):
        wizard = self._get_wizard()
        wizard.step = 'preferences'
        wizard.action_previous()
        self.assertEqual(wizard.step, 'about')

    def test_age_gate_field_exists_on_profile(self):
        Profile = self.env['club_social_profile.profile']
        self.assertIn('age_gate_passed', Profile._fields)

    def test_full_flow_without_age_gate(self):
        """welcome → about → age_gate → confirm → preferences → done."""
        user3, profile3 = _make_member(self.env, 'WizUser3', 'wiz_user3', age_gate_passed=False)
        wizard = self._get_wizard(user=user3)
        wizard.step = 'welcome'
        wizard.action_next()
        self.assertEqual(wizard.step, 'about')
        wizard.action_next()
        self.assertEqual(wizard.step, 'age_gate')
        wizard.age_gate_confirmed = True
        wizard.action_next()
        self.assertEqual(wizard.step, 'preferences')
        if 'privacy_policy_accepted' in wizard._fields:  # social_privacy installé
            wizard.privacy_policy_accepted = True
        wizard.action_finish()
        self.assertTrue(profile3.sudo().onboarding_done)
        self.assertTrue(profile3.sudo().age_gate_passed)

    def test_full_flow_already_gated(self):
        """welcome → about → preferences (age_gate skipped)."""
        user4, profile4 = _make_member(self.env, 'WizUser4', 'wiz_user4', age_gate_passed=True)
        wizard = self._get_wizard(user=user4)
        wizard.step = 'welcome'
        wizard.action_next()
        self.assertEqual(wizard.step, 'about')
        wizard.action_next()
        self.assertEqual(wizard.step, 'preferences')

    def test_age_gate_passed_helper_no_profile(self):
        """_age_gate_passed() retourne False quand profile_id est vide."""
        wizard = self.env['social_onboarding.wizard'].create({})
        self.assertFalse(wizard._age_gate_passed())

    def test_age_gate_passed_helper_with_gated_profile(self):
        user5, profile5 = _make_member(self.env, 'WizUser5', 'wiz_user5', age_gate_passed=True)
        wizard = self._get_wizard(user=user5)
        self.assertTrue(wizard._age_gate_passed())

    def test_age_gate_confirmed_default_false(self):
        wizard = self._get_wizard()
        self.assertFalse(wizard.age_gate_confirmed)
