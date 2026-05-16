from odoo.tests import HttpCase, TransactionCase, tagged


def _make_social_user(env, name, login):
    group_social = env.ref('social_base.group_social_user')
    return env['res.users'].create({
        'name': name, 'login': login, 'email': f'{login}@search.test',
        'group_ids': [(4, group_social.id)],
    })


@tagged('social_search', 'search_portal')
class TestSearchPortalData(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = _make_social_user(cls.env, 'SearchPortalUser', 'search_portal_user')
        cls.profile = cls.env['club_social_profile.profile'].sudo().get_or_create_for_user(cls.user)

    def test_search_all_empty_query_returns_results(self):
        results = self.env['social_search.service'].with_user(self.user).search_all('')
        self.assertIsInstance(results, dict)
        for t in ('profile', 'group', 'post', 'gallery', 'event'):
            self.assertIn(t, results)

    def test_search_profile_by_name(self):
        results = self.env['social_search.service'].with_user(self.user).search_all(
            'SearchPortalUser', types=['profile']
        )
        self.assertIn('profile', results)
        names = [r['name'] for r in results['profile']]
        self.assertIn('SearchPortalUser', names)

    def test_search_with_type_filter(self):
        results = self.env['social_search.service'].with_user(self.user).search_all(
            '', types=['profile']
        )
        self.assertIn('profile', results)
        self.assertNotIn('post', results)

    def test_search_invalid_type_ignored(self):
        results = self.env['social_search.service'].with_user(self.user).search_all(
            '', types=['profile', 'invalid_type']
        )
        self.assertIn('profile', results)
        self.assertNotIn('invalid_type', results)

    def test_search_limit_respected(self):
        results = self.env['social_search.service'].with_user(self.user).search_all(
            '', limit=3, types=['profile']
        )
        self.assertLessEqual(len(results.get('profile', [])), 3)

    def test_search_profile_result_structure(self):
        results = self.env['social_search.service'].with_user(self.user).search_all(
            'SearchPortalUser', types=['profile']
        )
        for item in results.get('profile', []):
            self.assertIn('type', item)
            self.assertIn('id', item)
            self.assertIn('name', item)
            self.assertEqual(item['type'], 'profile')

    def test_search_group_result_structure(self):
        group = self.env['social_group.group'].sudo().create({
            'name': 'Search Test Group', 'privacy': 'public',
            'join_type': 'open', 'creator_id': self.user.id,
        })
        results = self.env['social_search.service'].with_user(self.user).search_all(
            'Search Test Group', types=['group']
        )
        for item in results.get('group', []):
            self.assertIn('type', item)
            self.assertIn('id', item)
            self.assertIn('member_count', item)

    def test_search_gallery_result_has_url(self):
        gallery = self.env['social_gallery.gallery'].sudo().create({
            'name': 'Search Test Gallery', 'owner_id': self.user.id,
            'visibility': 'members',
        })
        results = self.env['social_search.service'].with_user(self.user).search_all(
            'Search Test Gallery', types=['gallery']
        )
        for item in results.get('gallery', []):
            self.assertIn('url', item)
            self.assertTrue(item['url'].startswith('/gallery/'))

    def test_search_profile_result_has_url(self):
        results = self.env['social_search.service'].with_user(self.user).search_all(
            'SearchPortalUser', types=['profile']
        )
        for item in results.get('profile', []):
            self.assertIn('url', item)
            self.assertIn('/profile/', item['url'])

    def test_search_event_result_has_url(self):
        if 'event.event' not in self.env:
            self.skipTest('event.event not installed')
        import datetime
        now = datetime.datetime.now()
        event = self.env['event.event'].sudo().create({
            'name': 'Search URL Test Event',
            'date_begin': now,
            'date_end': now + datetime.timedelta(hours=2),
            'social_visibility': 'members',
        })
        results = self.env['social_search.service'].with_user(self.user).search_all(
            'Search URL Test Event', types=['event']
        )
        for item in results.get('event', []):
            self.assertIn('url', item)
            self.assertIn('/event/', item['url'])

    def test_search_respects_blocked_users(self):
        blocked_user = _make_social_user(self.env, 'BlockedSearchUser', 'blocked_search')
        self.env['club_social_profile.profile'].sudo().get_or_create_for_user(blocked_user)
        self.env['social_safety.block'].sudo().create({
            'blocker_id': self.user.id,
            'blocked_id': blocked_user.id,
        })
        results = self.env['social_search.service'].with_user(self.user).search_all(
            'BlockedSearchUser', types=['profile']
        )
        names = [r['name'] for r in results.get('profile', [])]
        self.assertNotIn('BlockedSearchUser', names)


@tagged('social_search', 'search_portal', 'post_install', '-at_install')
class TestSearchPortalHttp(HttpCase):

    def test_search_unauthenticated_redirects(self):
        resp = self.url_open('/search', allow_redirects=False)
        self.assertIn(resp.status_code, (302, 303))

    def test_search_authenticated_empty_ok(self):
        self.authenticate('admin', 'admin')
        resp = self.url_open('/search')
        self.assertEqual(resp.status_code, 200)

    def test_search_with_query_ok(self):
        self.authenticate('admin', 'admin')
        resp = self.url_open('/search?q=admin')
        self.assertEqual(resp.status_code, 200)

    def test_search_type_filter_profile(self):
        self.authenticate('admin', 'admin')
        resp = self.url_open('/search?q=admin&types=profile')
        self.assertEqual(resp.status_code, 200)

    def test_search_type_filter_group(self):
        self.authenticate('admin', 'admin')
        resp = self.url_open('/search?q=&types=group')
        self.assertEqual(resp.status_code, 200)

    def test_search_type_filter_gallery(self):
        self.authenticate('admin', 'admin')
        resp = self.url_open('/search?q=&types=gallery')
        self.assertEqual(resp.status_code, 200)

    def test_search_empty_query_shows_placeholder(self):
        self.authenticate('admin', 'admin')
        resp = self.url_open('/search')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'Entrez un terme', resp.content)

    # ── API /social/api/search ────────────────────────────────────────────────

    def test_api_search_unauthenticated_redirects(self):
        resp = self.url_open('/social/api/search', allow_redirects=False)
        self.assertIn(resp.status_code, (302, 303))

    def test_api_search_authenticated_returns_json(self):
        self.authenticate('admin', 'admin')
        resp = self.url_open('/social/api/search?q=admin')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()['data']
        self.assertIn('results', data)
        self.assertIn('total', data)

    def test_api_search_type_filter(self):
        self.authenticate('admin', 'admin')
        resp = self.url_open('/social/api/search?q=&types=profile')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()['data']
        self.assertIn('profile', data['results'])
        self.assertNotIn('post', data['results'])

    def test_api_search_empty_query_returns_results(self):
        self.authenticate('admin', 'admin')
        resp = self.url_open('/social/api/search')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()['data']
        self.assertIsInstance(data['total'], int)

    def test_api_search_limit_param(self):
        self.authenticate('admin', 'admin')
        resp = self.url_open('/social/api/search?q=&limit=2&types=profile')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()['data']
        self.assertLessEqual(len(data['results'].get('profile', [])), 2)

    def test_api_search_query_field_in_response(self):
        self.authenticate('admin', 'admin')
        resp = self.url_open('/social/api/search?q=test')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()['data']
        self.assertEqual(data['query'], 'test')
