import datetime
import math
from datetime import timezone

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

    # ── Relevance scoring : tests unitaires sur _score_item ───────────────────

    def _fake_ctx(self, connection_ids=None):
        return {
            'user': self.alice,
            'blocked_ids': [],
            'connection_user_ids': list(connection_ids or []),
            'member_group_ids': [],
            'circle_ids': [],
        }

    def _now_utc(self):
        return datetime.datetime.now(tz=timezone.utc)

    def _ts(self, hours_ago=0, hours_from_now=None):
        """Retourne un timestamp ISO en UTC décalé d'un nombre d'heures."""
        now = self._now_utc()
        if hours_from_now is not None:
            dt = now + datetime.timedelta(hours=hours_from_now)
        else:
            dt = now - datetime.timedelta(hours=hours_ago)
        return dt.isoformat()

    def test_score_recent_higher_than_old(self):
        """Un item récent doit scorer plus haut qu'un item identique mais ancien."""
        ctx = self._fake_ctx()
        now = self._now_utc()
        conn_set = set()
        Feed = self.Feed.with_user(self.alice)
        recent = {'item_type': 'post', 'timestamp': self._ts(hours_ago=1),
                  'author_id': 999, 'like_count': 0, 'comment_count': 0,
                  'view_count': 0, 'vote_count': 0}
        old = {'item_type': 'post', 'timestamp': self._ts(hours_ago=72),
               'author_id': 999, 'like_count': 0, 'comment_count': 0,
               'view_count': 0, 'vote_count': 0}
        self.assertGreater(
            Feed._score_item(recent, ctx, now, conn_set),
            Feed._score_item(old, ctx, now, conn_set),
        )

    def test_score_connection_boost(self):
        """Un post d'une connexion doit scorer ×1.5 vs. un étranger, toutes choses égales."""
        ctx = self._fake_ctx(connection_ids=[42])
        now = self._now_utc()
        conn_set = {42}
        Feed = self.Feed.with_user(self.alice)
        ts = self._ts(hours_ago=5)
        base_item = {'item_type': 'post', 'timestamp': ts,
                     'like_count': 0, 'comment_count': 0,
                     'view_count': 0, 'vote_count': 0}
        from_connection = dict(base_item, author_id=42)
        from_stranger = dict(base_item, author_id=99)
        score_conn = Feed._score_item(from_connection, ctx, now, conn_set)
        score_str = Feed._score_item(from_stranger, ctx, now, conn_set)
        self.assertAlmostEqual(score_conn / score_str, 1.5, places=5)

    def test_score_engagement_boost(self):
        """Plus d'engagement (likes, comments) → score plus élevé."""
        ctx = self._fake_ctx()
        now = self._now_utc()
        conn_set = set()
        Feed = self.Feed.with_user(self.alice)
        ts = self._ts(hours_ago=5)
        no_engage = {'item_type': 'post', 'timestamp': ts, 'author_id': 1,
                     'like_count': 0, 'comment_count': 0,
                     'view_count': 0, 'vote_count': 0}
        high_engage = {'item_type': 'post', 'timestamp': ts, 'author_id': 1,
                       'like_count': 50, 'comment_count': 20,
                       'view_count': 0, 'vote_count': 0}
        self.assertGreater(
            Feed._score_item(high_engage, ctx, now, conn_set),
            Feed._score_item(no_engage, ctx, now, conn_set),
        )

    def test_score_event_close_boost(self):
        """Un event dans 3 jours doit scorer ×2 vs. un event dans 60 jours."""
        ctx = self._fake_ctx()
        now = self._now_utc()
        conn_set = set()
        Feed = self.Feed.with_user(self.alice)
        soon = {'item_type': 'event',
                'timestamp': self._ts(hours_from_now=72),
                'date_begin': self._ts(hours_from_now=72),
                'like_count': 0, 'comment_count': 0,
                'view_count': 0, 'vote_count': 0}
        far = {'item_type': 'event',
               'timestamp': self._ts(hours_from_now=1440),
               'date_begin': self._ts(hours_from_now=1440),
               'like_count': 0, 'comment_count': 0,
               'view_count': 0, 'vote_count': 0}
        # soon has type_boost=2.0, far has type_boost=1.0 (>30 days)
        # both have decay≈1.0 (future timestamps → age_hours=0)
        self.assertGreater(
            Feed._score_item(soon, ctx, now, conn_set),
            Feed._score_item(far, ctx, now, conn_set),
        )

    def test_score_proposal_closing_soon_boost(self):
        """Une proposition qui ferme dans 12h doit scorer ×2 vs. dans 7 jours."""
        ctx = self._fake_ctx()
        now = self._now_utc()
        conn_set = set()
        Feed = self.Feed.with_user(self.alice)
        base = {'item_type': 'proposal',
                'timestamp': self._ts(hours_ago=5),
                'like_count': 0, 'comment_count': 0,
                'view_count': 0, 'vote_count': 0}
        closing_soon = dict(base, voting_closes_at=self._ts(hours_from_now=12))
        closing_far = dict(base, voting_closes_at=self._ts(hours_from_now=168))
        self.assertGreater(
            Feed._score_item(closing_soon, ctx, now, conn_set),
            Feed._score_item(closing_far, ctx, now, conn_set),
        )

    def test_score_story_boost(self):
        """Les stories ont un boost fixe ×1.2 vs. un post identique."""
        ctx = self._fake_ctx()
        now = self._now_utc()
        conn_set = set()
        Feed = self.Feed.with_user(self.alice)
        ts = self._ts(hours_ago=2)
        story = {'item_type': 'story', 'timestamp': ts, 'author_id': 1,
                 'like_count': 0, 'comment_count': 0,
                 'view_count': 0, 'vote_count': 0}
        post = {'item_type': 'post', 'timestamp': ts, 'author_id': 1,
                'like_count': 0, 'comment_count': 0,
                'view_count': 0, 'vote_count': 0}
        self.assertAlmostEqual(
            Feed._score_item(story, ctx, now, conn_set) /
            Feed._score_item(post, ctx, now, conn_set),
            1.2,
            places=5,
        )

    # ── Relevance sort : tests d'intégration ─────────────────────────────────

    def test_relevance_sort_items_have_score_field(self):
        """Avec sort='relevance', chaque item doit avoir un champ 'score'."""
        result = self.Feed.with_user(self.alice).get_feed(limit=10, sort='relevance')
        for item in result['items']:
            self.assertIn('score', item)
            self.assertIsInstance(item['score'], float)

    def test_recent_sort_items_have_no_score_field(self):
        """Avec sort='recent', les items ne doivent pas avoir de champ 'score'."""
        result = self.Feed.with_user(self.alice).get_feed(limit=10, sort='recent')
        for item in result['items']:
            self.assertNotIn('score', item)

    def test_relevance_sort_result_structure(self):
        """get_feed(sort='relevance') doit retourner la même structure que 'recent'."""
        result = self.Feed.with_user(self.alice).get_feed(limit=5, sort='relevance')
        self.assertIn('items', result)
        self.assertIn('has_more', result)
        self.assertIsInstance(result['items'], list)

    def test_relevance_sort_pagination_no_overlap(self):
        """La pagination doit fonctionner sans chevauchement avec sort='relevance'."""
        result_p1 = self.Feed.with_user(self.alice).get_feed(limit=5, offset=0, sort='relevance')
        result_p2 = self.Feed.with_user(self.alice).get_feed(limit=5, offset=5, sort='relevance')
        ids_p1 = [(i['item_type'], i['id']) for i in result_p1['items']]
        ids_p2 = [(i['item_type'], i['id']) for i in result_p2['items']]
        self.assertFalse(set(ids_p1) & set(ids_p2), 'Les pages ne doivent pas se chevaucher')

    def test_relevance_connection_post_ranks_above_stranger(self):
        """Un post d'une connexion doit apparaître avant le même post d'un inconnu."""
        # Bob est connecté à Alice ; Carol est inconnue d'Alice
        self.env['club_social_profile.connection'].sudo().create({
            'user_id': self.alice.id,
            'connected_user_id': self.bob.id,
            'connection_type': 'friend',
            'state': 'accepted',
        })
        post_from_connection = self._make_post(self.bob, visibility='members',
                                               content='post connexion relevance')
        post_from_stranger = self._make_post(self.carol, visibility='members',
                                             content='post inconnu relevance')
        result = self.Feed.with_user(self.alice).get_feed(
            types=['post'], sort='relevance'
        )
        ids = [i['id'] for i in result['items'] if i['item_type'] == 'post']
        # Les deux posts doivent être présents
        self.assertIn(post_from_connection.id, ids)
        self.assertIn(post_from_stranger.id, ids)
        # Le post de la connexion doit apparaître avant celui de l'inconnu
        idx_conn = ids.index(post_from_connection.id)
        idx_str = ids.index(post_from_stranger.id)
        self.assertLess(idx_conn, idx_str)
