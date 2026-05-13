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
            'join_policy': 'open',
        })
        results = self.Search.with_user(self.bob)._search_groups('Groupe Public Srch', 20, 0)
        ids = [r['id'] for r in results]
        self.assertIn(group.id, ids)

    def test_group_private_visible_to_non_member(self):
        group = self.env['social_group.group'].sudo().create({
            'name': 'Groupe Privé Srch',
            'creator_id': self.alice.id,
            'privacy': 'private',
            'join_policy': 'approval',
        })
        results = self.Search.with_user(self.bob)._search_groups('Groupe Privé Srch', 20, 0)
        ids = [r['id'] for r in results]
        self.assertIn(group.id, ids)

    def test_group_secret_hidden_from_non_member(self):
        group = self.env['social_group.group'].sudo().create({
            'name': 'Groupe Secret Srch',
            'creator_id': self.alice.id,
            'privacy': 'secret',
            'join_policy': 'approval',
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
            'join_policy': 'approval',
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
        circle = self.env['social_circles.circle'].create({
            'profile_id': self.alice_profile.id,
            'name': 'Test Circle',
        })
        event = self._make_event('Événement Cercle Srch', visibility='circles', circles=circle)
        results = self.Search.with_user(self.carol)._search_events('Événement Cercle Srch', 20, 0)
        ids = [r['id'] for r in results]
        self.assertNotIn(event.id, ids)

    def test_event_circles_visible_to_circle_member(self):
        circle = self.env['social_circles.circle'].create({
            'profile_id': self.alice_profile.id,
            'name': 'Test Circle Visible',
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
