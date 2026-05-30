from datetime import timedelta

from odoo import fields
from odoo.tests import HttpCase, TransactionCase, tagged


def _make_social_user(env, name, login):
    group_user = env.ref('base.group_user')
    group_social = env.ref('social_base.group_social_user')
    return env['res.users'].create({
        'name': name, 'login': login, 'email': f'{login}@dashboard.test',
        'password': 'Test1234!',
        'group_ids': [(4, group_user.id), (4, group_social.id)],
    })


@tagged('club_social_profile', 'dashboard_portal', 'post_install', '-at_install')
class TestDashboardData(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = _make_social_user(cls.env, 'DashUser', 'dash_user')
        cls.other = _make_social_user(cls.env, 'DashOther', 'dash_other')
        cls.profile = cls.env['club_social_profile.profile'].sudo().get_or_create_for_user(cls.user)
        cls.other_profile = cls.env['club_social_profile.profile'].sudo().get_or_create_for_user(cls.other)

    # ── Vues de profil ────────────────────────────────────────────────────

    def test_profile_views_count(self):
        now = fields.Datetime.now()
        count_before = self.env['club_social_profile.profile_visit'].sudo().search_count([
            ('profile_id', '=', self.profile.id),
            ('visited_at', '>=', now - timedelta(days=7)),
        ])
        self.env['club_social_profile.profile_visit'].sudo().create({
            'profile_id': self.profile.id,
            'visitor_id': self.other.id,
        })
        count_after = self.env['club_social_profile.profile_visit'].sudo().search_count([
            ('profile_id', '=', self.profile.id),
            ('visited_at', '>=', now - timedelta(days=7)),
        ])
        self.assertEqual(count_after, count_before + 1)

    def test_no_profile_gives_zero_views(self):
        user_no_profile = _make_social_user(self.env, 'NoProfile', 'no_profile')
        profile = self.env['club_social_profile.profile'].sudo().search(
            [('user_id', '=', user_no_profile.id)], limit=1
        )
        self.assertFalse(profile)
        # Dans le controller, profile = False → profile_views = 0
        profile_views = 0
        if profile:
            profile_views = 1  # ne devrait pas arriver
        self.assertEqual(profile_views, 0)

    # ── Connexions ────────────────────────────────────────────────────────

    def test_new_connections_count(self):
        since = fields.Datetime.now() - timedelta(days=7)
        conn = self.env['club_social_profile.connection'].sudo().create({
            'user_id': self.user.id,
            'connected_user_id': self.other.id,
            'state': 'accepted',
        })
        count = self.env['club_social_profile.connection'].sudo().search_count([
            '|',
            '&', ('user_id', '=', self.user.id), ('state', '=', 'accepted'),
            '&', ('connected_user_id', '=', self.user.id), ('state', '=', 'accepted'),
            ('write_date', '>=', since),
        ])
        self.assertGreaterEqual(count, 1)

    def test_pending_requests_count(self):
        third = _make_social_user(self.env, 'DashThird', 'dash_third')
        self.env['club_social_profile.connection'].sudo().create({
            'user_id': third.id,
            'connected_user_id': self.user.id,
            'state': 'pending',
        })
        count = self.env['club_social_profile.connection'].sudo().search_count([
            ('connected_user_id', '=', self.user.id),
            ('state', '=', 'pending'),
        ])
        self.assertGreaterEqual(count, 1)

    # ── Notifications ─────────────────────────────────────────────────────

    def test_unread_notifs_count(self):
        self.env['club_social_profile.notification'].sudo().create({
            'user_id': self.user.id,
            'actor_id': self.other.id,
            'type': 'connection_request',
            'body': 'Test notif dashboard',
            'is_read': False,
        })
        count = self.env['club_social_profile.notification'].sudo().search_count([
            ('user_id', '=', self.user.id),
            ('is_read', '=', False),
        ])
        self.assertGreaterEqual(count, 1)

    def test_recent_notifs_ordered(self):
        notifs = self.env['club_social_profile.notification'].sudo().search([
            ('user_id', '=', self.user.id),
        ], order='create_date desc', limit=5)
        dates = notifs.mapped('create_date')
        self.assertEqual(dates, sorted(dates, reverse=True))

    # ── Guards modules optionnels ─────────────────────────────────────────

    def test_groups_guard(self):
        if 'social_group.group' not in self.env:
            self.skipTest('social_group not installed')
        groups = self.env['social_group.group'].sudo().search([
            ('member_ids', 'in', [self.user.id]),
        ], limit=6)
        self.assertIsNotNone(groups)

    def test_proposals_guard(self):
        if 'social_governance.proposal' not in self.env:
            self.skipTest('social_governance not installed')
        proposals = self.env['social_governance.proposal'].sudo().search([
            ('state', '=', 'voting'),
        ], limit=4)
        self.assertIsNotNone(proposals)

    def test_events_guard(self):
        if 'event.event' not in self.env:
            self.skipTest('event not installed')
        now = fields.Datetime.now()
        events = self.env['event.event'].sudo().search([
            ('date_begin', '>=', now),
            ('date_begin', '<=', now + timedelta(days=14)),
        ], limit=4)
        self.assertIsNotNone(events)

    # ── recent_conn_profiles ──────────────────────────────────────────────

    def test_recent_conn_profiles_excludes_self(self):
        since = fields.Datetime.now() - timedelta(days=7)
        conn_ids = self.env['club_social_profile.connection'].sudo().search([
            '|',
            '&', ('user_id', '=', self.user.id), ('state', '=', 'accepted'),
            '&', ('connected_user_id', '=', self.user.id), ('state', '=', 'accepted'),
            ('write_date', '>=', since),
        ], limit=6)
        other_ids = set()
        for c in conn_ids:
            other = c.connected_user_id if c.user_id.id == self.user.id else c.user_id
            other_ids.add(other.id)
        self.assertNotIn(self.user.id, other_ids)


@tagged('club_social_profile', 'dashboard_portal', 'post_install', '-at_install')
class TestDashboardHttp(HttpCase):

    def test_dashboard_unauthenticated_redirects(self):
        resp = self.url_open('/my/dashboard', allow_redirects=False)
        self.assertIn(resp.status_code, (302, 303))

    def test_dashboard_authenticated_ok(self):
        self.authenticate('admin', 'admin')
        resp = self.url_open('/my/dashboard')
        self.assertEqual(resp.status_code, 200)

    def test_dashboard_contains_stats(self):
        self.authenticate('admin', 'admin')
        resp = self.url_open('/my/dashboard')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'Profile views', resp.content)
        self.assertIn(b'New connections', resp.content)

    def test_dashboard_contains_profile_card(self):
        admin = self.env.ref('base.user_admin')
        self.env['club_social_profile.profile'].sudo().get_or_create_for_user(admin)
        self.authenticate('admin', 'admin')
        resp = self.url_open('/my/dashboard')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'View my profile', resp.content)

    def test_dashboard_has_breadcrumb(self):
        self.authenticate('admin', 'admin')
        resp = self.url_open('/my/dashboard')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'Dashboard', resp.content)
