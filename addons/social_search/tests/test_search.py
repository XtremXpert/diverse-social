import datetime

from odoo.tests import TransactionCase, tagged


@tagged('social_search', 'search')
class TestSocialSearch(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        group_social = cls.env.ref('social_base.group_social_user')
        group_mod = cls.env.ref('social_base.group_social_moderator')
        group_event_desk = cls.env.ref('event.group_event_registration_desk')
        group_event_user = cls.env.ref('event.group_event_user')

        def make_user(name, login, extra_groups=None):
            groups = [(4, group_social.id), (4, group_event_desk.id)]
            for g in (extra_groups or []):
                groups.append((4, g.id))
            return cls.env['res.users'].create({
                'name': name, 'login': login, 'email': f'{login}@search.test',
                'group_ids': groups,
            })

        cls.alice = make_user('Alice Recherche', 'srch_alice',
                              extra_groups=[group_mod, group_event_user])
        cls.bob = make_user('Bob Recherche', 'srch_bob')
        cls.carol = make_user('Carol Recherche', 'srch_carol')

        cls.Profile = cls.env['club_social_profile.profile']
        cls.alice_profile = cls.Profile.get_or_create_for_user(cls.alice)
        cls.bob_profile = cls.Profile.get_or_create_for_user(cls.bob)
        cls.carol_profile = cls.Profile.get_or_create_for_user(cls.carol)

        cls.alice_profile.sudo().write({'visibility': 'members', 'city': 'Montréal'})
        cls.bob_profile.sudo().write({'visibility': 'members'})
        cls.carol_profile.sudo().write({'visibility': 'connections'})

        cls.Search = cls.env['social_search.service']

    # ── Profiles ──────────────────────────────────────────────────────────────

    def test_profile_search_by_name(self):
        results = self.Search.with_user(self.alice)._search_profiles('Bob Recherche', 20, 0)
        ids = [r['id'] for r in results]
        self.assertIn(self.bob_profile.id, ids)

    def test_profile_search_by_city(self):
        results = self.Search.with_user(self.alice)._search_profiles('Montréal', 20, 0)
        ids = [r['id'] for r in results]
        self.assertIn(self.alice_profile.id, ids)

    def test_profile_connections_only_hidden_from_strangers(self):
        results = self.Search.with_user(self.alice)._search_profiles('Carol Recherche', 20, 0)
        ids = [r['id'] for r in results]
        self.assertNotIn(self.carol_profile.id, ids)

    def test_profile_connections_only_visible_to_connection(self):
        self.env['club_social_profile.connection'].sudo().create({
            'user_id': self.alice.id,
            'connected_user_id': self.carol.id,
            'connection_type': 'friend',
            'state': 'accepted',
        })
        results = self.Search.with_user(self.alice)._search_profiles('Carol Recherche', 20, 0)
        ids = [r['id'] for r in results]
        self.assertIn(self.carol_profile.id, ids)

    def test_profile_blocked_user_excluded(self):
        self.env['social_safety.block'].with_user(self.alice).block_user(self.bob)
        try:
            results = self.Search.with_user(self.alice)._search_profiles('Bob Recherche', 20, 0)
            ids = [r['id'] for r in results]
            self.assertNotIn(self.bob_profile.id, ids)
        finally:
            self.env['social_safety.block'].with_user(self.alice).unblock_user(self.bob)

    def test_profile_empty_query_returns_all_visible(self):
        results = self.Search.with_user(self.alice)._search_profiles('', 50, 0)
        self.assertGreater(len(results), 0)

    # ── Groups ────────────────────────────────────────────────────────────────

    def test_group_public_visible_to_all(self):
        group = self.env['social_group.group'].sudo().create({
            'name': 'Groupe Public Srch',
            'creator_id': self.alice.id,
            'privacy': 'public',
            'join_type': 'open',
        })
        results = self.Search.with_user(self.bob)._search_groups('Groupe Public Srch', 20, 0)
        ids = [r['id'] for r in results]
        self.assertIn(group.id, ids)

    def test_group_private_visible_to_non_member(self):
        group = self.env['social_group.group'].sudo().create({
            'name': 'Groupe Privé Srch',
            'creator_id': self.alice.id,
            'privacy': 'private',
            'join_type': 'approval',
        })
        results = self.Search.with_user(self.bob)._search_groups('Groupe Privé Srch', 20, 0)
        ids = [r['id'] for r in results]
        self.assertIn(group.id, ids)

    def test_group_secret_hidden_from_non_member(self):
        group = self.env['social_group.group'].sudo().create({
            'name': 'Groupe Secret Srch',
            'creator_id': self.alice.id,
            'privacy': 'secret',
            'join_type': 'approval',
        })
        results = self.Search.with_user(self.bob)._search_groups('Groupe Secret Srch', 20, 0)
        ids = [r['id'] for r in results]
        self.assertNotIn(group.id, ids)

    def test_group_secret_visible_to_member(self):
        group = self.env['social_group.group'].sudo().create({
            'name': 'Groupe Secret Membre Srch',
            'creator_id': self.alice.id,
            'member_ids': [(4, self.bob.id)],
            'privacy': 'secret',
            'join_type': 'approval',
        })
        results = self.Search.with_user(self.bob)._search_groups('Groupe Secret Membre Srch', 20, 0)
        ids = [r['id'] for r in results]
        self.assertIn(group.id, ids)

    # ── Events ────────────────────────────────────────────────────────────────

    def _make_event(self, name, visibility='members', circles=None):
        now = datetime.datetime.now()
        vals = {
            'name': name,
            'date_begin': now,
            'date_end': now + datetime.timedelta(hours=2),
            'organizer_user_id': self.alice.id,
            'social_visibility': visibility,
        }
        if circles:
            vals['allowed_circle_ids'] = [(6, 0, circles.ids)]
        return self.env['event.event'].with_user(self.alice).create(vals)

    def test_event_members_visible_to_all(self):
        event = self._make_event('Événement Members Srch', visibility='members')
        results = self.Search.with_user(self.bob)._search_events('Événement Members Srch', 20, 0)
        ids = [r['id'] for r in results]
        self.assertIn(event.id, ids)

    def test_event_circles_hidden_from_outsider(self):
        circle_type = self.env['social_circles.circle_type'].create({'name': 'Test Type Search'})
        circle = self.env['social_circles.circle'].create({
            'profile_id': self.alice_profile.id,
            'name': 'Test Circle',
            'type_id': circle_type.id,
        })
        event = self._make_event('Événement Cercle Srch', visibility='circles', circles=circle)
        results = self.Search.with_user(self.carol)._search_events('Événement Cercle Srch', 20, 0)
        ids = [r['id'] for r in results]
        self.assertNotIn(event.id, ids)

    def test_event_circles_visible_to_circle_member(self):
        circle_type = self.env['social_circles.circle_type'].create({'name': 'Test Type Search Visible'})
        circle = self.env['social_circles.circle'].create({
            'profile_id': self.alice_profile.id,
            'name': 'Test Circle Visible',
            'type_id': circle_type.id,
        })
        circle.add_member(self.bob)
        event = self._make_event('Événement Cercle Visible Srch', visibility='circles', circles=circle)
        results = self.Search.with_user(self.bob)._search_events('Événement Cercle Visible Srch', 20, 0)
        ids = [r['id'] for r in results]
        self.assertIn(event.id, ids)

    # ── Posts ─────────────────────────────────────────────────────────────────

    def _make_post(self, content, visibility='members', author=None, state='published'):
        author = author or self.alice
        return self.env['social_base.post'].sudo().create({
            'name': f'Post {content[:20]}',
            'content': f'<p>{content}</p>',
            'author_id': author.id,
            'visibility': visibility,
            'state': state,
        })

    def test_post_members_visible(self):
        post = self._make_post('Contenu recherchable membres')
        results = self.Search.with_user(self.bob)._search_posts('recherchable membres', 20, 0)
        ids = [r['id'] for r in results]
        self.assertIn(post.id, ids)

    def test_post_draft_not_visible(self):
        post = self._make_post('Contenu brouillon recherche', state='draft')
        results = self.Search.with_user(self.bob)._search_posts('brouillon recherche', 20, 0)
        ids = [r['id'] for r in results]
        self.assertNotIn(post.id, ids)

    def test_post_by_blocked_user_excluded(self):
        post = self._make_post('Post par utilisateur bloqué', author=self.bob)
        self.env['social_safety.block'].with_user(self.alice).block_user(self.bob)
        try:
            results = self.Search.with_user(self.alice)._search_posts('utilisateur bloqué', 20, 0)
            ids = [r['id'] for r in results]
            self.assertNotIn(post.id, ids)
        finally:
            self.env['social_safety.block'].with_user(self.alice).unblock_user(self.bob)

    # ── search_all ────────────────────────────────────────────────────────────

    def test_search_all_returns_all_types(self):
        results = self.Search.with_user(self.alice).search_all('Recherche', limit=5)
        self.assertIn('profile', results)
        self.assertIn('group', results)
        self.assertIn('event', results)
        self.assertIn('post', results)

    def test_search_all_filter_by_type(self):
        results = self.Search.with_user(self.alice).search_all(
            'Recherche', limit=5, types=['profile', 'group']
        )
        self.assertIn('profile', results)
        self.assertIn('group', results)
        self.assertNotIn('event', results)
        self.assertNotIn('post', results)

    def test_search_all_invalid_type_ignored(self):
        results = self.Search.with_user(self.alice).search_all(
            'test', limit=5, types=['profile', 'inexistant']
        )
        self.assertIn('profile', results)
        self.assertNotIn('inexistant', results)

    def test_limit_capped_at_max(self):
        results = self.Search.with_user(self.alice).search_all('', limit=999)
        for items in results.values():
            self.assertLessEqual(len(items), 50)

    # ── Dict helpers ──────────────────────────────────────────────────────────

    def test_profile_to_dict_bio_truncated(self):
        """bio tronquée à 120 caractères."""
        self.alice_profile.sudo().write({'bio': 'A' * 200})
        results = self.Search.with_user(self.alice)._search_profiles('Alice Recherche', 20, 0)
        item = next(r for r in results if r['id'] == self.alice_profile.id)
        self.assertEqual(len(item['bio']), 120)

    def test_profile_to_dict_keys(self):
        results = self.Search.with_user(self.alice)._search_profiles('Bob Recherche', 20, 0)
        item = next(r for r in results if r['id'] == self.bob_profile.id)
        for key in ('type', 'id', 'user_id', 'name', 'login', 'city', 'bio', 'url'):
            self.assertIn(key, item)
        self.assertEqual(item['type'], 'profile')
        self.assertTrue(item['url'].startswith('/profile/'))

    def test_post_to_dict_html_stripped(self):
        """excerpt ne contient pas de balises HTML."""
        post = self.env['social_base.post'].sudo().create({
            'name': 'Post HTML Strip',
            'content': '<p>Contenu <b>en gras</b> test strip</p>',
            'author_id': self.alice.id,
            'visibility': 'members',
            'state': 'published',
        })
        results = self.Search.with_user(self.alice)._search_posts('test strip', 20, 0)
        item = next((r for r in results if r['id'] == post.id), None)
        self.assertIsNotNone(item)
        self.assertNotIn('<', item['excerpt'])
        self.assertNotIn('>', item['excerpt'])

    def test_post_to_dict_keys_and_visibility(self):
        post = self.env['social_base.post'].sudo().create({
            'name': 'Post Dict Keys',
            'content': '<p>Contenu clés</p>',
            'author_id': self.alice.id,
            'visibility': 'public',
            'state': 'published',
        })
        results = self.Search.with_user(self.alice)._search_posts('Contenu clés', 20, 0)
        item = next((r for r in results if r['id'] == post.id), None)
        self.assertIsNotNone(item)
        for key in ('type', 'id', 'name', 'excerpt', 'author', 'create_date', 'visibility'):
            self.assertIn(key, item)
        self.assertEqual(item['visibility'], 'public')

    def test_event_to_dict_organizer(self):
        import datetime
        now = datetime.datetime.now()
        event = self.env['event.event'].with_user(self.alice).create({
            'name': 'Événement Organisateur Srch',
            'date_begin': now,
            'date_end': now + datetime.timedelta(hours=2),
            'organizer_user_id': self.alice.id,
            'social_visibility': 'members',
        })
        results = self.Search.with_user(self.alice)._search_events('Organisateur Srch', 20, 0)
        item = next((r for r in results if r['id'] == event.id), None)
        self.assertIsNotNone(item)
        self.assertEqual(item['organizer'], self.alice.name)

    def test_gallery_to_dict_is_shared(self):
        gallery = self.env['social_gallery.gallery'].sudo().create({
            'name': 'Galerie Partagée Srch',
            'owner_id': self.alice.id,
            'visibility': 'members',
            'is_shared': True,
        })
        results = self.Search.with_user(self.alice)._search_galleries('Partagée Srch', 20, 0)
        item = next((r for r in results if r['id'] == gallery.id), None)
        self.assertIsNotNone(item)
        self.assertTrue(item['is_shared'])

    def test_gallery_private_excluded(self):
        """Les galeries privées ne sont pas retournées."""
        gallery = self.env['social_gallery.gallery'].sudo().create({
            'name': 'Galerie Privée Srch',
            'owner_id': self.alice.id,
            'visibility': 'private',
        })
        results = self.Search.with_user(self.alice)._search_galleries('Privée Srch', 20, 0)
        ids = [r['id'] for r in results]
        self.assertNotIn(gallery.id, ids)

    def test_offset_pagination(self):
        """offset décale les résultats de manière cohérente."""
        results_p0 = self.Search.with_user(self.alice)._search_profiles('', 1, 0)
        results_p1 = self.Search.with_user(self.alice)._search_profiles('', 1, 1)
        if results_p0 and results_p1:
            self.assertNotEqual(results_p0[0]['id'], results_p1[0]['id'])

    def test_get_search_types_returns_expected(self):
        types = self.Search.with_user(self.alice)._get_search_types()
        for t in ('profile', 'group', 'event', 'post', 'gallery'):
            self.assertIn(t, types)
