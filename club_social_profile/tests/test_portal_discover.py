from odoo.tests import HttpCase, TransactionCase, tagged


def _make_member(env, name, login, **profile_vals):
    group_user = env.ref('base.group_user')
    group_social = env.ref('social_base.group_social_user')
    user = env['res.users'].create({
        'name': name, 'login': login, 'email': f'{login}@disc.test',
        'password': 'Test1234!',
        'group_ids': [(4, group_user.id), (4, group_social.id)],
    })
    profile = env['club_social_profile.profile'].sudo().get_or_create_for_user(user)
    if profile_vals:
        profile.sudo().write(profile_vals)
    return user, profile


def _connect(env, user_a, user_b):
    env['club_social_profile.connection'].sudo().create([
        {'user_id': user_a.id, 'connected_user_id': user_b.id, 'state': 'accepted'},
        {'user_id': user_b.id, 'connected_user_id': user_a.id, 'state': 'accepted'},
    ])


@tagged('club_social_profile', 'portal_discover', 'post_install', '-at_install')
class TestPortalDiscoverData(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.u_montreal, cls.p_montreal = _make_member(
            cls.env, 'DiscMontreal', 'disc_montreal',
            city='Montréal', gender='femme', orientation='bi',
            availability='disponible', visibility='members',
        )
        cls.u_quebec, cls.p_quebec = _make_member(
            cls.env, 'DiscQuebec', 'disc_quebec',
            city='Québec', gender='homme', orientation='hetero',
            availability='couple_ouvert', visibility='members',
        )
        cls.u_hidden, cls.p_hidden = _make_member(
            cls.env, 'DiscHidden', 'disc_hidden',
            visibility='connections',
        )
        cls.searcher, _ = _make_member(
            cls.env, 'DiscSearcher', 'disc_searcher',
            visibility='members',
        )
        cls.Profile = cls.env['club_social_profile.profile']

    def _search(self, **filters):
        """Helper: mimics the controller domain."""
        from odoo.addons.club_social_profile.controllers.portal_discover import (
            _gender_labels, _orientation_labels, _availability_labels,
        )
        domain = [
            ('user_id', '!=', self.searcher.id),
            ('visibility', '=', 'members'),
        ]
        if filters.get('city'):
            domain.append(('city', 'ilike', filters['city']))
        if filters.get('gender') and filters['gender'] in _gender_labels():
            domain.append(('gender', '=', filters['gender']))
        if filters.get('orientation') and filters['orientation'] in _orientation_labels():
            domain.append(('orientation', '=', filters['orientation']))
        if filters.get('availability') and filters['availability'] in _availability_labels():
            domain.append(('availability', '=', filters['availability']))
        return self.Profile.sudo().search(domain)

    # ── Visibility ───────────────────────────────────────────────────────

    def test_members_visible_profiles_included(self):
        results = self._search()
        self.assertIn(self.p_montreal, results)
        self.assertIn(self.p_quebec, results)

    def test_connections_only_profile_excluded(self):
        results = self._search()
        self.assertNotIn(self.p_hidden, results)

    def test_own_profile_excluded(self):
        domain = [('user_id', '!=', self.searcher.id), ('visibility', '=', 'members')]
        results = self.Profile.sudo().search(domain)
        searcher_profile = self.Profile.sudo().search([('user_id', '=', self.searcher.id)], limit=1)
        self.assertNotIn(searcher_profile, results)

    # ── Filtres ───────────────────────────────────────────────────────────

    def test_filter_by_city(self):
        results = self._search(city='Montréal')
        self.assertIn(self.p_montreal, results)
        self.assertNotIn(self.p_quebec, results)

    def test_filter_by_city_ilike(self):
        results = self._search(city='montréal')
        self.assertIn(self.p_montreal, results)

    def test_filter_by_gender(self):
        results = self._search(gender='femme')
        self.assertIn(self.p_montreal, results)
        self.assertNotIn(self.p_quebec, results)

    def test_filter_by_orientation(self):
        results = self._search(orientation='bi')
        self.assertIn(self.p_montreal, results)
        self.assertNotIn(self.p_quebec, results)

    def test_filter_by_availability(self):
        results = self._search(availability='disponible')
        self.assertIn(self.p_montreal, results)
        self.assertNotIn(self.p_quebec, results)

    def test_filter_invalid_gender_ignored(self):
        results = self._search(gender='invalid_value')
        self.assertIn(self.p_montreal, results)

    def test_combined_filters(self):
        results = self._search(city='Montréal', gender='femme', orientation='bi')
        self.assertIn(self.p_montreal, results)
        self.assertNotIn(self.p_quebec, results)

    def test_no_results_on_tight_filters(self):
        results = self._search(city='Paris')
        self.assertFalse(results.filtered(
            lambda p: p.id in [self.p_montreal.id, self.p_quebec.id]
        ))

    # ── Filtrage des non-membres (sans group_social_user) ─────────────────

    def test_user_without_social_group_excluded(self):
        """A user with a profile but no group_social_user (e.g. admin who
        visited /my/profile/edit) must NOT appear in /discover listings.

        Reproduces the production scenario where admin.id=2 was showing
        up as a member card on diverse-cite.com."""
        sponsorless = self.env['res.users'].create({
            'name': 'NoSponsor', 'login': 'no_sponsor_data',
            'email': 'no_sponsor_data@disc.test', 'password': 'Test1234!',
            'group_ids': [(4, self.env.ref('base.group_user').id)],
        })
        sponsorless_profile = self.Profile.sudo().get_or_create_for_user(sponsorless)
        sponsorless_profile.sudo().write({'visibility': 'members'})
        social_group_id = self.env.ref('social_base.group_social_user').id
        domain = [
            ('user_id', '!=', self.searcher.id),
            ('visibility', '=', 'members'),
            ('user_id.all_group_ids', 'in', [social_group_id]),
        ]
        results = self.Profile.sudo().search(domain)
        self.assertNotIn(sponsorless_profile, results)
        self.assertIn(self.p_montreal, results)

    # ── Blocage ───────────────────────────────────────────────────────────

    def test_blocked_user_excluded(self):
        if 'social_safety.block' not in self.env:
            self.skipTest('social_safety not installed')
        self.env['social_safety.block'].sudo().block_user(self.u_montreal)
        blocked_ids = self.env['social_safety.block'].sudo().get_blocked_ids_for(self.env.user)
        domain = [
            ('user_id', '!=', self.env.user.id),
            ('visibility', '=', 'members'),
            ('user_id', 'not in', list(blocked_ids)),
        ]
        results = self.Profile.sudo().search(domain)
        self.assertNotIn(self.p_montreal, results)


@tagged('club_social_profile', 'portal_discover', 'post_install', '-at_install')
class TestPortalDiscoverHttp(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        admin = cls.env.ref('base.user_admin')
        group_social = cls.env.ref('social_base.group_social_user')
        admin.sudo().write({'group_ids': [(4, group_social.id)]})
        cls.env['club_social_profile.profile'].sudo().get_or_create_for_user(admin)
        u1, p1 = cls._create_disc_user(cls.env)
        cls.disc_user = u1
        cls.disc_profile = p1

    @classmethod
    def _create_disc_user(cls, env):
        group_user = env.ref('base.group_user')
        group_social = env.ref('social_base.group_social_user')
        u1 = env['res.users'].create({
            'name': 'DiscHTTP1', 'login': 'disc_http1_class',
            'email': 'disc_http1_class@disc.test', 'password': 'Test1234!',
            'group_ids': [(4, group_user.id), (4, group_social.id)],
        })
        p1 = env['club_social_profile.profile'].sudo().get_or_create_for_user(u1)
        p1.sudo().write({
            'city': 'Laval', 'gender': 'homme',
            'availability': 'disponible', 'visibility': 'members',
        })
        return u1, p1

    def _setup(self):
        group_user = self.env.ref('base.group_user')
        group_social = self.env.ref('social_base.group_social_user')
        u1 = self.env['res.users'].create({
            'name': 'DiscHTTP1', 'login': 'disc_http1',
            'email': 'disc_http1@disc.test', 'password': 'Test1234!',
            'group_ids': [(4, group_user.id), (4, group_social.id)],
        })
        p1 = self.env['club_social_profile.profile'].sudo().get_or_create_for_user(u1)
        p1.sudo().write({
            'city': 'Laval', 'gender': 'homme',
            'availability': 'disponible', 'visibility': 'members',
        })
        return u1, p1

    def test_discover_unauthenticated_redirects(self):
        resp = self.url_open('/discover', allow_redirects=False)
        self.assertIn(resp.status_code, (302, 303))

    def test_discover_authenticated_ok(self):
        self.authenticate('admin', 'admin')
        resp = self.url_open('/discover')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'Discover members', resp.content)

    def test_discover_shows_member_profiles(self):
        self.authenticate('admin', 'admin')
        resp = self.url_open('/discover')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'disc_http1_class', resp.content)

    def test_discover_filter_by_city(self):
        self.authenticate('admin', 'admin')
        resp = self.url_open('/discover?city=Laval')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'disc_http1_class', resp.content)

    def test_discover_filter_city_no_match(self):
        self.authenticate('admin', 'admin')
        resp = self.url_open('/discover?city=ZZZVilleInexistante')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'0 member', resp.content)

    def test_discover_filter_gender(self):
        self.authenticate('admin', 'admin')
        resp = self.url_open('/discover?gender=homme')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'disc_http1_class', resp.content)

    def test_discover_filter_availability(self):
        self.authenticate('admin', 'admin')
        resp = self.url_open('/discover?availability=disponible')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'disc_http1_class', resp.content)

    def test_discover_connections_only_not_shown(self):
        group_user = self.env.ref('base.group_user')
        group_social = self.env.ref('social_base.group_social_user')
        hidden_user = self.env['res.users'].create({
            'name': 'DiscHiddenHTTP', 'login': 'disc_hidden_http',
            'email': 'disc_hidden_http@disc.test', 'password': 'Test1234!',
            'group_ids': [(4, group_user.id), (4, group_social.id)],
        })
        hidden_profile = self.env['club_social_profile.profile'].sudo().get_or_create_for_user(hidden_user)
        hidden_profile.sudo().write({'visibility': 'connections'})
        self.authenticate('admin', 'admin')
        resp = self.url_open('/discover')
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn(b'DiscHiddenHTTP', resp.content)

    def test_discover_has_filter_form(self):
        self.authenticate('admin', 'admin')
        resp = self.url_open('/discover')
        self.assertEqual(resp.status_code, 200)
        # Tolère un préfixe de langue (/en, /fr) ajouté en site multilingue.
        self.assertRegex(resp.content, rb'action="[^"]*/discover"')

    def test_discover_invalid_filter_ignored(self):
        self.authenticate('admin', 'admin')
        resp = self.url_open('/discover?gender=invalid_value')
        self.assertEqual(resp.status_code, 200)

    def test_discover_excludes_sponsorless_user(self):
        """A user with a profile but no group_social_user (typical of an
        admin who happened to visit /my/profile/edit) does not appear in
        /discover."""
        group_user = self.env.ref('base.group_user')
        sponsorless = self.env['res.users'].create({
            'name': 'NoSponsorHTTP', 'login': 'no_sponsor_http',
            'email': 'no_sponsor_http@disc.test', 'password': 'Test1234!',
            'group_ids': [(4, group_user.id)],
        })
        profile = self.env['club_social_profile.profile'].sudo().get_or_create_for_user(sponsorless)
        profile.sudo().write({'visibility': 'members', 'city': 'Laval'})
        self.authenticate('admin', 'admin')
        resp = self.url_open('/discover')
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn(b'NoSponsorHTTP', resp.content)
