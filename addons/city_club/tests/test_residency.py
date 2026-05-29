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

        # Test DB may already carry a default resident type if a leaf module
        # (e.g. st_isidore_city_club) is installed alongside city_club. The
        # constraint allows only one active default — deactivate any pre-existing
        # one for the duration of the test class.
        existing_default = cls.env['club_membership.type'].search([
            ('is_resident_default', '=', True),
            ('active', '=', True),
        ])
        existing_default.write({'is_resident_default': False})

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

    def test_submit_notifies_moderators(self):
        # Spin up a fresh moderator to receive the notif (the test class doesn't
        # ship one, which is also why the other tests don't trigger this path).
        moderator_group = self.env.ref('social_base.group_social_moderator')
        moderator = self.env['res.users'].create({
            'name': 'Mod', 'login': 'mod@stisidore.example',
            'group_ids': [(4, moderator_group.id)],
        })

        self.profile.action_submit_residency(postal_code='G0S 2S0')

        notifs = self.env['club_social_profile.notification'].sudo().search([
            ('user_id', '=', moderator.id),
            ('type', '=', 'residency_pending'),
        ])
        self.assertEqual(len(notifs), 1)
        self.assertEqual(notifs.actor_id, self.user)
        self.assertEqual(notifs.ref_model, 'club_social_profile.profile')
        self.assertEqual(notifs.ref_id, self.profile.id)

    def test_resubmit_pending_does_not_duplicate_notif(self):
        moderator_group = self.env.ref('social_base.group_social_moderator')
        self.env['res.users'].create({
            'name': 'Mod', 'login': 'mod2@stisidore.example',
            'group_ids': [(4, moderator_group.id)],
        })
        self.profile.action_submit_residency(postal_code='G0S 2S0')
        # Idempotent — second call while state=pending should not re-notify.
        self.profile.action_submit_residency(postal_code='G0S 2S0')
        count = self.env['club_social_profile.notification'].sudo().search_count([
            ('type', '=', 'residency_pending'),
            ('actor_id', '=', self.user.id),
        ])
        self.assertEqual(count, 1)
