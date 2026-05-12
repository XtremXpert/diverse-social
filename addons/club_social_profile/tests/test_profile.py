from odoo.tests import TransactionCase, tagged
from odoo.exceptions import ValidationError


@tagged('club_social_profile', 'profile')
class TestClubSocialProfile(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = cls.env.ref('base.user_demo')
        cls.Profile = cls.env['club_social_profile.profile']

    def test_get_or_create(self):
        profile = self.Profile.get_or_create_for_user(self.user)
        self.assertEqual(profile.user_id, self.user)
        # Idempotent
        profile2 = self.Profile.get_or_create_for_user(self.user)
        self.assertEqual(profile, profile2)

    def test_unique_user_constraint(self):
        self.Profile.get_or_create_for_user(self.user)
        with self.assertRaises(ValidationError):
            self.Profile.create({'user_id': self.user.id})

    def test_age_computation(self):
        from datetime import date
        profile = self.Profile.get_or_create_for_user(self.user)
        profile.birth_year = date.today().year - 30
        self.assertEqual(profile.age, 30)
        self.assertTrue(profile.age_verified)

    def test_minor_rejected(self):
        from datetime import date
        profile = self.Profile.get_or_create_for_user(self.user)
        with self.assertRaises(ValidationError):
            profile.birth_year = date.today().year - 15
            profile._check_birth_year_adult()

    def test_default_visibility(self):
        profile = self.Profile.get_or_create_for_user(self.user)
        self.assertEqual(profile.visibility, 'members')
