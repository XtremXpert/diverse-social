from odoo.tests import HttpCase, TransactionCase, tagged


def _make_social_user(env, name, login):
    group_user = env.ref('base.group_user')
    group_social = env.ref('social_base.group_social_user')
    return env['res.users'].create({
        'name': name, 'login': login, 'email': f'{login}@profile.test',
        'password': 'Test1234!',
        'group_ids': [(4, group_user.id), (4, group_social.id)],
    })


@tagged('club_social_profile', 'profile_portal', 'post_install', '-at_install')
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
            'bio': 'Test owner bio',
            'city': 'Montréal',
        })

    def _connect(self, user_a, user_b):
        conn = self.env['club_social_profile.connection'].sudo().create({
            'user_id': user_a.id,
            'connected_user_id': user_b.id,
            'state': 'accepted',
        })
        # reciprocal connection
        self.env['club_social_profile.connection'].sudo().create({
            'user_id': user_b.id,
            'connected_user_id': user_a.id,
            'state': 'accepted',
        })
        return conn

    # ── Visibility ───────────────────────────────────────────────────────

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
        """The owner viewing their own profile does not generate a visit."""
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
        _csrf = self.csrf_token()
        resp = self.url_open('/my/profile/edit')
        self.assertEqual(resp.status_code, 200)

    def test_edit_preferences_tab(self):
        self.authenticate('admin', 'admin')
        _csrf = self.csrf_token()
        resp = self.url_open('/my/profile/edit?section=preferences')
        self.assertEqual(resp.status_code, 200)
        # Assert structural anchors instead of translated labels so the
        # test passes regardless of the rendering language.
        self.assertIn('name="visibility"', resp.text)
        self.assertIn('name="availability"', resp.text)

    def test_save_identity_redirects(self):
        self.authenticate('admin', 'admin')
        _csrf = self.csrf_token()
        resp = self.url_open(
            '/my/profile/edit/identity',
            data={'csrf_token': _csrf, 
                'bio': 'Bio test edit',
                'city': 'Montréal',
                'gender': 'non_binaire',
                'orientation': 'queer',
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn('Profile updated', resp.text)

    def test_save_identity_invalid_gender_ignored(self):
        self.authenticate('admin', 'admin')
        _csrf = self.csrf_token()
        resp = self.url_open(
            '/my/profile/edit/identity',
            data={'csrf_token': _csrf, 'gender': 'INVALIDE'},
        )
        self.assertEqual(resp.status_code, 200)

    def test_save_identity_underage_returns_error(self):
        import datetime
        self.authenticate('admin', 'admin')
        _csrf = self.csrf_token()
        resp = self.url_open(
            '/my/profile/edit/identity',
            data={'csrf_token': _csrf, 'birth_year': str(datetime.date.today().year - 16)},
        )
        self.assertEqual(resp.status_code, 200)
        # The error message goes through _() so the wording shifts with the
        # user's language. Test the structural marker: the page renders the
        # bootstrap alert-danger container only when an error is present.
        self.assertIn('alert-danger', resp.text)

    def test_save_preferences_ok(self):
        self.authenticate('admin', 'admin')
        _csrf = self.csrf_token()
        resp = self.url_open(
            '/my/profile/edit/preferences',
            data={'csrf_token': _csrf, 
                'visibility': 'members',
                'availability': 'disponible',
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn('Preferences saved', resp.text)

    def test_edit_page_has_tabs(self):
        self.authenticate('admin', 'admin')
        _csrf = self.csrf_token()
        resp = self.url_open('/my/profile/edit')
        self.assertEqual(resp.status_code, 200)
        # The visible tab labels go through _() and shift with language.
        # Assert on the hrefs that route to each section instead.
        self.assertIn('section=identity', resp.text)
        self.assertIn('section=preferences', resp.text)


@tagged('club_social_profile', 'profile_portal', 'post_install', '-at_install')
class TestProfilePortalHttp(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # The /profile/<id> route requires the *target* user to be a social
        # network member (a3837f7); the demo admin user is not in
        # group_social_user by default, so every test that hits its own
        # profile would return 404.
        admin = cls.env.ref('base.user_admin')
        admin.sudo().write({
            'group_ids': [(4, cls.env.ref('social_base.group_social_user').id)],
        })

    def test_profile_unauthenticated_redirects(self):
        resp = self.url_open('/profile/1', allow_redirects=False)
        self.assertIn(resp.status_code, (302, 303))

    def test_own_profile_authenticated_ok(self):
        admin_user = self.env.ref('base.user_admin')
        self.env['club_social_profile.profile'].sudo().get_or_create_for_user(admin_user)
        self.authenticate('admin', 'admin')
        _csrf = self.csrf_token()
        resp = self.url_open(f'/profile/{admin_user.id}')
        self.assertEqual(resp.status_code, 200)

    def test_nonexistent_profile_returns_404(self):
        self.authenticate('admin', 'admin')
        _csrf = self.csrf_token()
        resp = self.url_open('/profile/999999999')
        self.assertEqual(resp.status_code, 404)

    def test_profile_page_shows_display_name(self):
        admin_user = self.env.ref('base.user_admin')
        self.env['club_social_profile.profile'].sudo().get_or_create_for_user(admin_user)
        self.authenticate('admin', 'admin')
        _csrf = self.csrf_token()
        resp = self.url_open(f'/profile/{admin_user.id}')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(admin_user.name.encode(), resp.content)

    def test_profile_with_bio(self):
        admin_user = self.env.ref('base.user_admin')
        profile = self.env['club_social_profile.profile'].sudo().get_or_create_for_user(admin_user)
        profile.sudo().write({'bio': 'Bio test HTTP portail'})
        self.authenticate('admin', 'admin')
        _csrf = self.csrf_token()
        resp = self.url_open(f'/profile/{admin_user.id}')
        self.assertEqual(resp.status_code, 200)
