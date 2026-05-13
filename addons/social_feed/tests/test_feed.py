import datetime

from odoo.tests import TransactionCase, tagged


@tagged('social_feed', 'feed')
class TestSocialFeed(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        group_social = cls.env.ref('social_base.group_social_user')
        group_mod = cls.env.ref('social_base.group_social_moderator')
        group_event_desk = cls.env.ref('event.group_event_registration_desk')
        group_event_user = cls.env.ref('event.group_event_user')

        def make_user(name, login, extra=None):
            groups = [(4, group_social.id), (4, group_event_desk.id)]
            for g in (extra or []):
                groups.append((4, g.id))
            return cls.env['res.users'].create({
                'name': name, 'login': login, 'email': f'{login}@feed.test',
                'group_ids': groups,
            })

        cls.alice = make_user('Alice Feed', 'feed_alice',
                              extra=[group_mod, group_event_user])
        cls.bob = make_user('Bob Feed', 'feed_bob')
        cls.carol = make_user('Carol Feed', 'feed_carol')

        cls.Profile = cls.env['club_social_profile.profile']
        cls.alice_profile = cls.Profile.get_or_create_for_user(cls.alice)

        cls.Feed = cls.env['social_feed.service']

    # ── Posts: visibility ────────────────────────────────────────────────────

    def _make_post(self, author, visibility='members', state='published', content='test'):
        return self.env['social_base.post'].sudo().create({
            'name': f'Post {visibility}',
            'content': f'<p>{content}</p>',
            'author_id': author.id,
            'visibility': visibility,
            'state': state,
        })

    def test_post_members_appears_in_feed(self):
        post = self._make_post(self.alice, visibility='members')
        result = self.Feed.with_user(self.bob).get_feed(types=['post'])
        ids = [i['id'] for i in result['items'] if i['item_type'] == 'post']
        self.assertIn(post.id, ids)

    def test_post_public_appears_in_feed(self):
        post = self._make_post(self.alice, visibility='public')
        result = self.Feed.with_user(self.carol).get_feed(types=['post'])
        ids = [i['id'] for i in result['items'] if i['item_type'] == 'post']
        self.assertIn(post.id, ids)

    def test_post_draft_excluded(self):
        post = self._make_post(self.alice, state='draft')
        result = self.Feed.with_user(self.bob).get_feed(types=['post'])
        ids = [i['id'] for i in result['items'] if i['item_type'] == 'post']
        self.assertNotIn(post.id, ids)

    def test_post_friends_hidden_from_non_connection(self):
        post = self._make_post(self.alice, visibility='friends')
        result = self.Feed.with_user(self.carol).get_feed(types=['post'])
        ids = [i['id'] for i in result['items'] if i['item_type'] == 'post']
        self.assertNotIn(post.id, ids)

    def test_post_friends_visible_to_connection(self):
        self.env['club_social_profile.connection'].sudo().create({
            'user_id': self.bob.id,
            'connected_user_id': self.alice.id,
            'connection_type': 'friend',
            'state': 'accepted',
        })
        post = self._make_post(self.alice, visibility='friends', content='pour amis')
        result = self.Feed.with_user(self.bob).get_feed(types=['post'])
        ids = [i['id'] for i in result['items'] if i['item_type'] == 'post']
        self.assertIn(post.id, ids)

    def test_post_private_only_visible_to_author(self):
        post = self._make_post(self.alice, visibility='private')
        result_bob = self.Feed.with_user(self.bob).get_feed(types=['post'])
        ids_bob = [i['id'] for i in result_bob['items'] if i['item_type'] == 'post']
        self.assertNotIn(post.id, ids_bob)
        result_alice = self.Feed.with_user(self.alice).get_feed(types=['post'])
        ids_alice = [i['id'] for i in result_alice['items'] if i['item_type'] == 'post']
        self.assertIn(post.id, ids_alice)

    def test_post_by_blocked_user_excluded(self):
        post = self._make_post(self.alice, content='post bloqué')
        self.env['social_safety.block'].with_user(self.bob).block_user(self.alice)
        try:
            result = self.Feed.with_user(self.bob).get_feed(types=['post'])
            ids = [i['id'] for i in result['items'] if i['item_type'] == 'post']
            self.assertNotIn(post.id, ids)
        finally:
            self.env['social_safety.block'].with_user(self.bob).unblock_user(self.alice)

    # ── Posts: group privacy ──────────────────────────────────────────────────

    def test_group_secret_post_hidden_from_non_member(self):
        group = self.env['social_group.group'].sudo().create({
            'name': 'Secret Group Feed',
            'creator_id': self.alice.id,
            'privacy': 'secret',
            'join_policy': 'approval',
        })
        post = self.env['social_base.post'].sudo().create({
            'name': 'Group Secret Post',
            'content': '<p>secret</p>',
            'author_id': self.alice.id,
            'visibility': 'members',
            'state': 'published',
            'group_id': group.id,
        })
        result = self.Feed.with_user(self.carol).get_feed(types=['post'])
        ids = [i['id'] for i in result['items'] if i['item_type'] == 'post']
        self.assertNotIn(post.id, ids)

    def test_group_secret_post_visible_to_member(self):
        group = self.env['social_group.group'].sudo().create({
            'name': 'Secret Group Feed Member',
            'creator_id': self.alice.id,
            'member_ids': [(4, self.bob.id)],
            'privacy': 'secret',
            'join_policy': 'approval',
        })
        post = self.env['social_base.post'].sudo().create({
            'name': 'Group Secret Post Visible',
            'content': '<p>secret visible</p>',
            'author_id': self.alice.id,
            'visibility': 'members',
            'state': 'published',
            'group_id': group.id,
        })
        result = self.Feed.with_user(self.bob).get_feed(types=['post'])
        ids = [i['id'] for i in result['items'] if i['item_type'] == 'post']
        self.assertIn(post.id, ids)

    # ── Stories ───────────────────────────────────────────────────────────────

    def test_story_from_connection_appears(self):
        self.env['club_social_profile.connection'].sudo().create({
            'user_id': self.carol.id,
            'connected_user_id': self.alice.id,
            'connection_type': 'friend',
            'state': 'accepted',
        })
        story = self.env['social_story.story'].sudo().create({
            'name': 'Story connexion feed',
            'author_id': self.alice.id,
        })
        result = self.Feed.with_user(self.carol).get_feed(types=['story'])
        ids = [i['id'] for i in result['items'] if i['item_type'] == 'story']
        self.assertIn(story.id, ids)

    def test_story_from_stranger_excluded(self):
        story = self.env['social_story.story'].sudo().create({
            'name': 'Story inconnu feed',
            'author_id': self.alice.id,
        })
        result = self.Feed.with_user(self.carol).get_feed(types=['story'])
        ids = [i['id'] for i in result['items'] if i['item_type'] == 'story']
        self.assertNotIn(story.id, ids)

    # ── Events ────────────────────────────────────────────────────────────────

    def test_upcoming_event_members_appears(self):
        now = datetime.datetime.now()
        event = self.env['event.event'].with_user(self.alice).create({
            'name': 'Événement Feed',
            'date_begin': now + datetime.timedelta(days=1),
            'date_end': now + datetime.timedelta(days=1, hours=2),
            'organizer_user_id': self.alice.id,
            'social_visibility': 'members',
        })
        result = self.Feed.with_user(self.bob).get_feed(types=['event'])
        ids = [i['id'] for i in result['items'] if i['item_type'] == 'event']
        self.assertIn(event.id, ids)

    def test_past_event_excluded(self):
        now = datetime.datetime.now()
        event = self.env['event.event'].with_user(self.alice).create({
            'name': 'Événement Passé Feed',
            'date_begin': now - datetime.timedelta(days=2),
            'date_end': now - datetime.timedelta(days=2, hours=-2),
            'organizer_user_id': self.alice.id,
            'social_visibility': 'members',
        })
        result = self.Feed.with_user(self.bob).get_feed(types=['event'])
        ids = [i['id'] for i in result['items'] if i['item_type'] == 'event']
        self.assertNotIn(event.id, ids)

    def test_circle_event_hidden_from_non_member(self):
        circle = self.env['social_circles.circle'].create({
            'profile_id': self.alice_profile.id,
            'name': 'Circle Feed',
        })
        now = datetime.datetime.now()
        event = self.env['event.event'].with_user(self.alice).create({
            'name': 'Événement Cercle Feed',
            'date_begin': now + datetime.timedelta(days=1),
            'date_end': now + datetime.timedelta(days=1, hours=2),
            'organizer_user_id': self.alice.id,
            'social_visibility': 'circles',
            'allowed_circle_ids': [(6, 0, [circle.id])],
        })
        result = self.Feed.with_user(self.carol).get_feed(types=['event'])
        ids = [i['id'] for i in result['items'] if i['item_type'] == 'event']
        self.assertNotIn(event.id, ids)

    # ── Proposals ─────────────────────────────────────────────────────────────

    def test_voting_proposal_appears(self):
        proposal = self.env['social_governance.proposal'].with_user(self.alice).create({
            'name': 'Proposition Feed',
            'description': '<p>détails</p>',
            'author_id': self.alice.id,
        })
        proposal.action_start_voting()
        result = self.Feed.with_user(self.bob).get_feed(types=['proposal'])
        ids = [i['id'] for i in result['items'] if i['item_type'] == 'proposal']
        self.assertIn(proposal.id, ids)

    def test_draft_proposal_excluded(self):
        proposal = self.env['social_governance.proposal'].with_user(self.alice).create({
            'name': 'Proposition Brouillon Feed',
            'description': '<p>détails</p>',
            'author_id': self.alice.id,
        })
        result = self.Feed.with_user(self.bob).get_feed(types=['proposal'])
        ids = [i['id'] for i in result['items'] if i['item_type'] == 'proposal']
        self.assertNotIn(proposal.id, ids)

    # ── Aggregation & pagination ──────────────────────────────────────────────

    def test_feed_all_types_present(self):
        result = self.Feed.with_user(self.alice).get_feed(limit=50)
        self.assertIn('items', result)
        self.assertIn('has_more', result)

    def test_feed_type_filter(self):
        result = self.Feed.with_user(self.alice).get_feed(types=['post'])
        for item in result['items']:
            self.assertEqual(item['item_type'], 'post')

    def test_feed_sorted_desc_by_timestamp(self):
        result = self.Feed.with_user(self.alice).get_feed(limit=50)
        timestamps = [i['timestamp'] for i in result['items'] if i['timestamp']]
        self.assertEqual(timestamps, sorted(timestamps, reverse=True))

    def test_feed_pagination(self):
        result_p1 = self.Feed.with_user(self.alice).get_feed(limit=5, offset=0)
        result_p2 = self.Feed.with_user(self.alice).get_feed(limit=5, offset=5)
        ids_p1 = [i['id'] for i in result_p1['items']]
        ids_p2 = [i['id'] for i in result_p2['items']]
        self.assertFalse(set(ids_p1) & set(ids_p2), 'Pages should not overlap')

    def test_limit_capped(self):
        result = self.Feed.with_user(self.alice).get_feed(limit=999)
        self.assertLessEqual(len(result['items']), 100)
