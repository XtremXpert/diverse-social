from odoo.tests import TransactionCase, tagged
from odoo.exceptions import ValidationError


@tagged('club_social_profile', 'profile')
class TestClubSocialProfile(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = cls.env['res.users'].create({
            'name': 'Profile Test User', 'login': 'profile_test_user', 'email': 'profile@test.test',
            'group_ids': [(4, cls.env.ref('social_base.group_social_user').id)],
        })
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

    def test_age_verified_false_no_birth_year(self):
        profile = self.Profile.get_or_create_for_user(self.user)
        profile.birth_year = 0
        self.assertFalse(profile.age_verified)

    def test_age_zero_when_no_birth_year(self):
        profile = self.Profile.get_or_create_for_user(self.user)
        profile.birth_year = 0
        self.assertEqual(profile.age, 0)

    def test_profile_login_matches_user(self):
        profile = self.Profile.get_or_create_for_user(self.user)
        self.assertEqual(profile.login, self.user.login)

    def test_partner_id_related(self):
        profile = self.Profile.get_or_create_for_user(self.user)
        self.assertEqual(profile.partner_id, self.user.partner_id)


@tagged('club_social_profile', 'notification')
class TestClubSocialNotification(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        group_user = cls.env.ref('social_base.group_social_user')
        cls.user_a = cls.env['res.users'].create({
            'name': 'Notif A', 'login': 'notif_a', 'email': 'notifia@test.test',
            'group_ids': [(4, group_user.id)],
        })
        cls.user_b = cls.env['res.users'].create({
            'name': 'Notif B', 'login': 'notif_b', 'email': 'notifib@test.test',
            'group_ids': [(4, group_user.id)],
        })
        cls.Notif = cls.env['club_social_profile.notification']

    def test_notify_creates_record(self):
        before = self.Notif.sudo().search_count([('user_id', '=', self.user_a.id)])
        self.Notif._notify(
            user_id=self.user_a.id,
            actor_id=self.user_b.id,
            notif_type='connection_request',
            body='Test notification',
        )
        after = self.Notif.sudo().search_count([('user_id', '=', self.user_a.id)])
        self.assertEqual(after, before + 1)

    def test_notify_self_ignored(self):
        """_notify n'envoie pas de notification si user_id == actor_id."""
        before = self.Notif.sudo().search_count([('user_id', '=', self.user_a.id)])
        self.Notif._notify(
            user_id=self.user_a.id,
            actor_id=self.user_a.id,
            notif_type='post_like',
            body='Autonotif',
        )
        after = self.Notif.sudo().search_count([('user_id', '=', self.user_a.id)])
        self.assertEqual(after, before)

    def test_notify_default_not_read(self):
        self.Notif._notify(
            user_id=self.user_a.id,
            actor_id=self.user_b.id,
            notif_type='post_comment',
            body='Commentaire',
        )
        notif = self.Notif.sudo().search([
            ('user_id', '=', self.user_a.id),
            ('type', '=', 'post_comment'),
        ], limit=1, order='id desc')
        self.assertFalse(notif.is_read)

    def test_action_mark_read(self):
        self.Notif._notify(
            user_id=self.user_a.id,
            actor_id=self.user_b.id,
            notif_type='new_message',
            body='Message',
        )
        notif = self.Notif.sudo().search([
            ('user_id', '=', self.user_a.id),
            ('type', '=', 'new_message'),
        ], limit=1, order='id desc')
        notif.action_mark_read()
        self.assertTrue(notif.is_read)
        self.assertTrue(notif.read_at)

    def test_mark_all_read_returns_count(self):
        self.Notif._notify(
            user_id=self.user_a.id,
            actor_id=self.user_b.id,
            notif_type='profile_visit',
            body='Visite',
        )
        count = self.Notif.with_user(self.user_a).mark_all_read(user_id=self.user_a.id)
        self.assertIsInstance(count, int)
        self.assertGreaterEqual(count, 1)

    def test_mark_all_read_sets_all_read(self):
        self.Notif._notify(
            user_id=self.user_a.id,
            actor_id=self.user_b.id,
            notif_type='connection_accepted',
            body='Connexion acceptée',
        )
        self.Notif.with_user(self.user_a).mark_all_read(user_id=self.user_a.id)
        remaining = self.Notif.sudo().search_count([
            ('user_id', '=', self.user_a.id),
            ('is_read', '=', False),
        ])
        self.assertEqual(remaining, 0)


@tagged('club_social_profile', 'profile_visit')
class TestProfileVisit(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        group_user = cls.env.ref('social_base.group_social_user')
        cls.owner = cls.env['res.users'].create({
            'name': 'Visit Owner', 'login': 'visit_owner', 'email': 'vowner@test.test',
            'group_ids': [(4, group_user.id)],
        })
        cls.visitor = cls.env['res.users'].create({
            'name': 'Visitor', 'login': 'visit_visitor', 'email': 'visitor@test.test',
            'group_ids': [(4, group_user.id)],
        })
        cls.profile = cls.env['club_social_profile.profile'].get_or_create_for_user(cls.owner)
        cls.visitor_profile = cls.env['club_social_profile.profile'].get_or_create_for_user(cls.visitor)

    def test_visit_creates_record(self):
        before = self.env['club_social_profile.profile_visit'].sudo().search_count([
            ('profile_id', '=', self.profile.id),
        ])
        self.env['club_social_profile.profile_visit'].sudo().create({
            'profile_id': self.profile.id,
            'visitor_id': self.visitor.id,
        })
        after = self.env['club_social_profile.profile_visit'].sudo().search_count([
            ('profile_id', '=', self.profile.id),
        ])
        self.assertEqual(after, before + 1)

    def test_visitor_profile_id_computed(self):
        visit = self.env['club_social_profile.profile_visit'].sudo().create({
            'profile_id': self.profile.id,
            'visitor_id': self.visitor.id,
        })
        self.assertEqual(visit.visitor_profile_id, self.visitor_profile)

    def test_visitor_profile_id_empty_without_profile(self):
        """Un visiteur sans profil laisse visitor_profile_id vide."""
        no_profile_user = self.env['res.users'].create({
            'name': 'No Profile', 'login': 'no_profile_visitor', 'email': 'noprofile@test.test',
        })
        visit = self.env['club_social_profile.profile_visit'].sudo().create({
            'profile_id': self.profile.id,
            'visitor_id': no_profile_user.id,
        })
        self.assertFalse(visit.visitor_profile_id)
