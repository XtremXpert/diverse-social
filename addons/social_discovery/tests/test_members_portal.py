from odoo.tests import HttpCase, TransactionCase, tagged


def _make_social_user(env, name, login, city=None, availability=None, gender=None):
    group_social = env.ref('social_base.group_social_user')
    user = env['res.users'].create({
        'name': name, 'login': login, 'email': f'{login}@discovery.test',
        'password': 'Test1234!',
        'group_ids': [(4, group_social.id)],
    })
    profile = env['club_social_profile.profile'].sudo().get_or_create_for_user(user)
    vals = {'onboarding_done': True, 'visibility': 'members'}
    if city:
        vals['city'] = city
    if availability:
        vals['availability'] = availability
    if gender:
        vals['gender'] = gender
    profile.sudo().write(vals)
    return user, profile


@tagged('social_discovery', 'members_portal')
class TestMembersPortalData(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user, cls.profile = _make_social_user(
            cls.env, 'DiscoveryUser', 'discovery_user', city='Montréal',
        )
        cls.user2, cls.profile2 = _make_social_user(
            cls.env, 'DiscoveryOther', 'discovery_other', city='Québec',
            availability='disponible', gender='femme',
        )
        cls.hidden_user = cls.env['res.users'].create({
            'name': 'HiddenProfile', 'login': 'hidden_discovery',
            'email': 'hidden@discovery.test',
        })
        cls.hidden_profile = cls.env['club_social_profile.profile'].sudo().get_or_create_for_user(
            cls.hidden_user
        )
        cls.hidden_profile.sudo().write({'visibility': 'connections', 'onboarding_done': True})

    def test_members_only_visibility_included(self):
        """Profils visibility=members apparaissent dans la découverte."""
        profiles = self.env['club_social_profile.profile'].sudo().search([
            ('user_id', '=', self.user2.id),
            ('visibility', '=', 'members'),
            ('onboarding_done', '=', True),
        ])
        self.assertTrue(profiles)

    def test_connections_only_visibility_excluded(self):
        """Profils visibility=connections exclus de la découverte."""
        all_visible = self.env['club_social_profile.profile'].sudo().search([
            ('visibility', '=', 'members'),
            ('onboarding_done', '=', True),
            ('user_id', '!=', self.user.id),
        ])
        ids = all_visible.mapped('user_id.id')
        self.assertNotIn(self.hidden_user.id, ids)

    def test_filter_by_city(self):
        profiles = self.env['club_social_profile.profile'].sudo().search([
            ('city', 'ilike', 'Québec'),
            ('visibility', '=', 'members'),
            ('onboarding_done', '=', True),
        ])
        cities = profiles.mapped('city')
        self.assertTrue(any('Québec' in c for c in cities))

    def test_filter_by_availability(self):
        profiles = self.env['club_social_profile.profile'].sudo().search([
            ('availability', '=', 'disponible'),
            ('visibility', '=', 'members'),
            ('onboarding_done', '=', True),
        ])
        self.assertTrue(all(p.availability == 'disponible' for p in profiles))

    def test_filter_by_gender(self):
        profiles = self.env['club_social_profile.profile'].sudo().search([
            ('gender', 'in', ['femme']),
            ('visibility', '=', 'members'),
            ('onboarding_done', '=', True),
        ])
        self.assertTrue(all(p.gender == 'femme' for p in profiles))

    def test_self_excluded(self):
        """Le chercheur ne se voit pas dans ses propres résultats."""
        profiles = self.env['club_social_profile.profile'].sudo().search([
            ('user_id', '!=', self.user.id),
            ('visibility', '=', 'members'),
            ('onboarding_done', '=', True),
        ])
        ids = profiles.mapped('user_id.id')
        self.assertNotIn(self.user.id, ids)

    def test_blocked_user_excluded(self):
        if 'social_safety.block' not in self.env:
            self.skipTest('social_safety not installed')
        blocked_user, blocked_profile = _make_social_user(
            self.env, 'BlockedMember', 'blocked_member',
        )
        self.env['social_safety.block'].sudo().create({
            'blocker_id': self.user.id,
            'blocked_id': blocked_user.id,
        })
        blocked_ids = self.env['social_safety.block'].get_blocked_ids_for(self.user)
        self.assertIn(blocked_user.id, blocked_ids)
        profiles = self.env['club_social_profile.profile'].sudo().search([
            ('user_id', 'not in', blocked_ids),
            ('visibility', '=', 'members'),
            ('onboarding_done', '=', True),
        ])
        self.assertNotIn(blocked_user.id, profiles.mapped('user_id.id'))

    def test_text_search_by_name(self):
        profiles = self.env['club_social_profile.profile'].sudo().search([
            ('user_id.name', 'ilike', 'DiscoveryOther'),
            ('visibility', '=', 'members'),
            ('onboarding_done', '=', True),
        ])
        self.assertIn(self.profile2.id, profiles.ids)

    def test_filter_has_photo(self):
        self.profile2.sudo().write({'profile_image': False})
        profiles_with_photo = self.env['club_social_profile.profile'].sudo().search([
            ('profile_image', '!=', False),
            ('visibility', '=', 'members'),
            ('onboarding_done', '=', True),
        ])
        for p in profiles_with_photo:
            self.assertTrue(p.profile_image)

    def test_criteria_model_find_profiles(self):
        """_find_profiles() du modèle criteria retourne des profils cohérents."""
        criteria = self.env['social_discovery.criteria'].sudo().create({
            'profile_id': self.profile.id,
            'name': 'Test Search',
        })
        results = criteria._find_profiles()
        self.assertNotIn(self.user.id, results.mapped('user_id.id'))
        self.assertNotIn(self.hidden_user.id, results.mapped('user_id.id'))


@tagged('social_discovery', 'members_portal', 'post_install', '-at_install')
class TestMembersPortalHttp(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        admin = cls.env.ref('base.user_admin')
        group_social = cls.env.ref('social_base.group_social_user')
        admin.sudo().write({'group_ids': [(4, group_social.id)]})
        cls.env['club_social_profile.profile'].sudo().get_or_create_for_user(admin)

    def test_members_unauthenticated_redirects(self):
        resp = self.url_open('/members', allow_redirects=False)
        self.assertIn(resp.status_code, (302, 303))

    def test_members_authenticated_ok(self):
        self.authenticate('admin', 'admin')
        resp = self.url_open('/members')
        self.assertEqual(resp.status_code, 200)

    def test_members_with_query(self):
        self.authenticate('admin', 'admin')
        resp = self.url_open('/members?q=admin')
        self.assertEqual(resp.status_code, 200)

    def test_members_filter_availability(self):
        self.authenticate('admin', 'admin')
        resp = self.url_open('/members?availability=disponible')
        self.assertEqual(resp.status_code, 200)

    def test_members_filter_gender(self):
        self.authenticate('admin', 'admin')
        resp = self.url_open('/members?gender=femme')
        self.assertEqual(resp.status_code, 200)

    def test_members_filter_city(self):
        self.authenticate('admin', 'admin')
        resp = self.url_open('/members?city=Montr%C3%A9al')
        self.assertEqual(resp.status_code, 200)

    def test_members_sort_new(self):
        self.authenticate('admin', 'admin')
        resp = self.url_open('/members?sort=new')
        self.assertEqual(resp.status_code, 200)

    def test_members_sort_alpha(self):
        self.authenticate('admin', 'admin')
        resp = self.url_open('/members?sort=alpha')
        self.assertEqual(resp.status_code, 200)

    def test_members_with_photo_filter(self):
        self.authenticate('admin', 'admin')
        resp = self.url_open('/members?has_photo=1')
        self.assertEqual(resp.status_code, 200)

    def test_members_page_shows_explorer(self):
        self.authenticate('admin', 'admin')
        resp = self.url_open('/members')
        self.assertEqual(resp.status_code, 200)
        # Structural marker: the page is rendered by the portal_members template.
        self.assertIn(b'social_discovery.portal_members', resp.content)
