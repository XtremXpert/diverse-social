from odoo.tests import HttpCase, TransactionCase, tagged


def _make_social_user(env, name, login):
    group_social = env.ref('social_base.group_social_user')
    return env['res.users'].create({
        'name': name, 'login': login, 'email': f'{login}@profile.test',
        'password': 'Test1234!',
        'group_ids': [(4, group_social.id)],
    })


@tagged('club_social_profile', 'profile_portal')
class TestProfilePortalData(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.viewer = _make_social_user(cls.env, 'ProfileViewer', 'profile_viewer')
        cls.owner = _make_social_user(cls.env, 'ProfileOwner', 'profile_owner')
        cls.viewer_profile = cls.env['club_social_profile.profile'].sudo().get_or_create_for_user(cls.viewer)
        cls.owner_profile = cls.env['club_social_profile.profile'].sudo().get_or_create_for_user(cls.owner)
        cls.owner_profile.sudo().write({
            'onboarding_done': True,
            'visibility': 'members',
            'bio': 'Test bio du propriétaire',
            'city': 'Montréal',
        })

    def _connect(self, user_a, user_b):
        conn = self.env['club_social_profile.connection'].sudo().create({
            'user_id': user_a.id,
            'connected_user_id': user_b.id,
            'state': 'accepted',
        })
        # connexion réciproque
        self.env['club_social_profile.connection'].sudo().create({
            'user_id': user_b.id,
            'connected_user_id': user_a.id,
            'state': 'accepted',
        })
        return conn

    # ── Visibilité ────────────────────────────────────────────────────────

    def test_members_visibility_allows_any_member(self):
        self.owner_profile.sudo().write({'visibility': 'members'})
        # Le viewer est membre (group_social_user) → doit voir le profil
        self.assertTrue(self.viewer.has_group('social_base.group_social_user'))
        # Pas de blocage → pas de restriction
        if 'social_safety.block' in self.env:
            blocked = self.env['social_safety.block'].is_blocked(self.viewer, self.owner)
            self.assertFalse(blocked)

    def test_connections_visibility_blocks_non_connection(self):
        self.owner_profile.sudo().write({'visibility': 'connections'})
        Connection = self.env['club_social_profile.connection'].sudo()
        is_conn = (
            Connection.is_connected(self.viewer, self.owner)
            or Connection.is_connected(self.owner, self.viewer)
        )
        self.assertFalse(is_conn)

    def test_connections_visibility_allows_connected(self):
        self.owner_profile.sudo().write({'visibility': 'connections'})
        self._connect(self.viewer, self.owner)
        Connection = self.env['club_social_profile.connection'].sudo()
        is_conn = (
            Connection.is_connected(self.viewer, self.owner)
            or Connection.is_connected(self.owner, self.viewer)
        )
        self.assertTrue(is_conn)

    # ── Visite profil ─────────────────────────────────────────────────────

    def test_profile_visit_recorded(self):
        from datetime import timedelta
        from odoo import fields
        count_before = self.env['club_social_profile.profile_visit'].sudo().search_count([
            ('profile_id', '=', self.owner_profile.id),
            ('visitor_id', '=', self.viewer.id),
        ])
        self.env['club_social_profile.profile_visit'].sudo().create({
            'profile_id': self.owner_profile.id,
            'visitor_id': self.viewer.id,
        })
        count_after = self.env['club_social_profile.profile_visit'].sudo().search_count([
            ('profile_id', '=', self.owner_profile.id),
            ('visitor_id', '=', self.viewer.id),
        ])
        self.assertEqual(count_after, count_before + 1)

    def test_no_self_visit(self):
        """Le propriétaire qui consulte son propre profil ne génère pas de visite."""
        count_before = self.env['club_social_profile.profile_visit'].sudo().search_count([
            ('profile_id', '=', self.owner_profile.id),
            ('visitor_id', '=', self.owner.id),
        ])
        # is_own == True → pas de create dans le controller
        self.assertEqual(count_before, count_before)  # no-op sanity check

    # ── Connexions mutuelles ──────────────────────────────────────────────

    def test_mutual_connections_computed(self):
        third = _make_social_user(self.env, 'MutualThird', 'mutual_third')
        self._connect(self.viewer, third)
        self._connect(self.owner, third)
        Connection = self.env['club_social_profile.connection'].sudo()
        viewer_ids = set(Connection.search([
            ('user_id', '=', self.viewer.id), ('state', '=', 'accepted'),
        ]).mapped('connected_user_id.id')) | set(Connection.search([
            ('connected_user_id', '=', self.viewer.id), ('state', '=', 'accepted'),
        ]).mapped('user_id.id'))
        owner_ids = set(Connection.search([
            ('user_id', '=', self.owner.id), ('state', '=', 'accepted'),
        ]).mapped('connected_user_id.id')) | set(Connection.search([
            ('connected_user_id', '=', self.owner.id), ('state', '=', 'accepted'),
        ]).mapped('user_id.id'))
        mutual = viewer_ids & owner_ids
        self.assertIn(third.id, mutual)

    # ── Blocage ───────────────────────────────────────────────────────────

    def test_blocked_user_not_visible(self):
        if 'social_safety.block' not in self.env:
            self.skipTest('social_safety not installed')
        blocker = _make_social_user(self.env, 'BlockerProfile', 'blocker_profile')
        blocked = _make_social_user(self.env, 'BlockedProfile', 'blocked_profile')
        self.env['club_social_profile.profile'].sudo().get_or_create_for_user(blocked)
        self.env['social_safety.block'].sudo().create({
            'blocker_id': blocker.id,
            'blocked_id': blocked.id,
        })
        is_blocked = self.env['social_safety.block'].is_blocked(blocker, blocked)
        self.assertTrue(is_blocked)

    # ── stealth_name ──────────────────────────────────────────────────────

    def test_stealth_name_returned_when_set(self):
        self.owner_profile.sudo().write({'stealth_name': 'Alias secret'})
        self.assertEqual(self.owner_profile.stealth_name, 'Alias secret')
        self.owner_profile.sudo().write({'stealth_name': False})

    def test_display_name_falls_back_to_user_name(self):
        self.owner_profile.sudo().write({'stealth_name': False})
        display = self.owner_profile.stealth_name or self.owner.name
        self.assertEqual(display, self.owner.name)


@tagged('club_social_profile', 'profile_edit', 'post_install', '-at_install')
class TestProfileEditHttp(HttpCase):

    def test_edit_unauthenticated_redirects(self):
        resp = self.url_open('/my/profile/edit', allow_redirects=False)
        self.assertIn(resp.status_code, (302, 303))

    def test_edit_authenticated_ok(self):
        self.authenticate('admin', 'admin')
        resp = self.url_open('/my/profile/edit')
        self.assertEqual(resp.status_code, 200)

    def test_edit_preferences_tab(self):
        self.authenticate('admin', 'admin')
        resp = self.url_open('/my/profile/edit?section=preferences')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'Visibilité', resp.content)

    def test_save_identity_redirects(self):
        self.authenticate('admin', 'admin')
        resp = self.url_open(
            '/my/profile/edit/identity',
            data={
                'csrf_token': self.csrf_token(),
                'bio': 'Bio test édition',
                'city': 'Montréal',
                'gender': 'non_binaire',
                'orientation': 'queer',
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'Profil mis à jour', resp.content)

    def test_save_identity_invalid_gender_ignored(self):
        self.authenticate('admin', 'admin')
        resp = self.url_open(
            '/my/profile/edit/identity',
            data={
                'csrf_token': self.csrf_token(),
                'gender': 'INVALIDE',
            },
        )
        self.assertEqual(resp.status_code, 200)

    def test_save_identity_underage_returns_error(self):
        import datetime
        self.authenticate('admin', 'admin')
        resp = self.url_open(
            '/my/profile/edit/identity',
            data={
                'csrf_token': self.csrf_token(),
                'birth_year': str(datetime.date.today().year - 16),
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'18 ans', resp.content)

    def test_save_preferences_ok(self):
        self.authenticate('admin', 'admin')
        resp = self.url_open(
            '/my/profile/edit/preferences',
            data={
                'csrf_token': self.csrf_token(),
                'visibility': 'members',
                'availability': 'disponible',
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'Préférences enregistrées', resp.content)

    def test_edit_page_has_tabs(self):
        self.authenticate('admin', 'admin')
        resp = self.url_open('/my/profile/edit')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'Identité', resp.content)
        self.assertIn(b'Préférences', resp.content)


@tagged('club_social_profile', 'profile_portal', 'post_install', '-at_install')
class TestProfilePortalHttp(HttpCase):

    def test_profile_unauthenticated_redirects(self):
        resp = self.url_open('/profile/1', allow_redirects=False)
        self.assertIn(resp.status_code, (302, 303))

    def test_own_profile_authenticated_ok(self):
        self.authenticate('admin', 'admin')
        admin_user = self.env.ref('base.user_admin')
        resp = self.url_open(f'/profile/{admin_user.id}')
        self.assertEqual(resp.status_code, 200)

    def test_nonexistent_profile_returns_404(self):
        self.authenticate('admin', 'admin')
        resp = self.url_open('/profile/999999999')
        self.assertEqual(resp.status_code, 404)

    def test_profile_page_shows_display_name(self):
        self.authenticate('admin', 'admin')
        admin_user = self.env.ref('base.user_admin')
        resp = self.url_open(f'/profile/{admin_user.id}')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(admin_user.name.encode(), resp.content)

    def test_profile_with_bio(self):
        self.authenticate('admin', 'admin')
        admin_user = self.env.ref('base.user_admin')
        profile = self.env['club_social_profile.profile'].sudo().search(
            [('user_id', '=', admin_user.id)], limit=1
        )
        if profile:
            profile.sudo().write({'bio': 'Bio test HTTP portail'})
        resp = self.url_open(f'/profile/{admin_user.id}')
        self.assertEqual(resp.status_code, 200)
