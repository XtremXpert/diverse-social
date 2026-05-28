from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, tagged


@tagged('city_club')
class TestResidency(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Param = cls.env['ir.config_parameter'].sudo()
        cls.Param.set_param('city_club.allowed_postal_prefix', 'G0S')
        cls.Param.set_param('city_club.allowed_postal_codes', '')

        cls.resident_type = cls.env['club_membership.type'].create({
            'name': 'Test resident',
            'duration_months': 0,
            'fee': 0.0,
            'is_resident_default': True,
        })
        cls.user = cls.env['res.users'].create({
            'name': 'Alice', 'login': 'alice@stisidore.example',
        })
        cls.profile = cls.env['club_social_profile.profile'].get_or_create_for_user(cls.user)

    def test_postal_allow_list_prefix(self):
        Profile = self.env['club_social_profile.profile']
        self.assertTrue(Profile._is_allowed_postal_code('G0S 2S0'))
        self.assertTrue(Profile._is_allowed_postal_code('g0s2s0'))
        self.assertFalse(Profile._is_allowed_postal_code('H2X 1Y4'))

    def test_postal_allow_list_full(self):
        self.Param.set_param('city_club.allowed_postal_prefix', '')
        self.Param.set_param('city_club.allowed_postal_codes', 'G0S 2S0, G0N 1A1')
        Profile = self.env['club_social_profile.profile']
        self.assertTrue(Profile._is_allowed_postal_code('G0S 2S0'))
        self.assertFalse(Profile._is_allowed_postal_code('G0S 1B2'))

    def test_postal_format_validation(self):
        with self.assertRaises(ValidationError):
            self.profile.residency_postal_code = 'not-a-code'

    def test_submit_then_verify_grants_membership(self):
        group = self.env.ref('social_base.group_social_user')
        self.assertNotIn(group, self.user.group_ids)

        self.profile.action_submit_residency(postal_code='G0S 2S0')
        self.assertEqual(self.profile.residency_state, 'pending')
        self.assertTrue(self.profile.residency_submitted_at)

        self.profile.action_verify_residency()
        self.assertEqual(self.profile.residency_state, 'verified')
        self.assertTrue(self.profile.residency_verified_at)
        self.assertEqual(self.profile.residency_verified_by_id, self.env.user)

        # Membership created and active
        membership = self.env['club_membership.membership'].search([
            ('partner_id', '=', self.user.partner_id.id),
        ], limit=1)
        self.assertEqual(membership.state, 'active')
        self.assertEqual(membership.membership_type_id, self.resident_type)

        # Group granted via standard membership workflow
        self.assertIn(group, self.user.group_ids)

    def test_verify_without_default_type_raises(self):
        self.resident_type.is_resident_default = False
        self.profile.action_submit_residency(postal_code='G0S 2S0')
        with self.assertRaises(UserError):
            self.profile.action_verify_residency()

    def test_only_one_default_resident_type(self):
        with self.assertRaises(ValidationError):
            self.env['club_membership.type'].create({
                'name': 'Second resident type',
                'is_resident_default': True,
            })

    def test_reject_then_reset(self):
        self.profile.action_submit_residency(postal_code='G0S 2S0')
        self.profile.action_reject_residency()
        self.assertEqual(self.profile.residency_state, 'rejected')
        self.profile.action_reset_residency()
        self.assertEqual(self.profile.residency_state, 'none')
        self.assertFalse(self.profile.residency_submitted_at)

    def test_no_config_means_open(self):
        self.Param.set_param('city_club.allowed_postal_prefix', '')
        self.Param.set_param('city_club.allowed_postal_codes', '')
        Profile = self.env['club_social_profile.profile']
        self.assertTrue(Profile._is_allowed_postal_code('Z9Z 9Z9'))

    def test_submit_disallowed_postal_raises(self):
        with self.assertRaises(UserError):
            self.profile.action_submit_residency(postal_code='H2X 1Y4')
        self.assertEqual(self.profile.residency_state, 'none')
