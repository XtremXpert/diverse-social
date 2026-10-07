import datetime
import math
from datetime import timezone

from odoo import fields
from odoo.tests import HttpCase, TransactionCase, tagged


@tagged('social_feed', 'feed')
class TestSocialFeed(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        group_user = cls.env.ref('base.group_user')
        group_social = cls.env.ref('social_base.group_social_user')
        group_mod = cls.env.ref('social_base.group_social_moderator')
        group_event_desk = cls.env.ref('event.group_event_registration_desk')
        group_event_user = cls.env.ref('event.group_event_user')

        def make_user(name, login, extra=None):
            groups = [(4, group_user.id), (4, group_social.id), (4, group_event_desk.id)]
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
            'join_type': 'approval',
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
            'join_type': 'approval',
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
        circle_type = self.env['social_circles.circle_type'].create({'name': 'Test Type Feed'})
        circle = self.env['social_circles.circle'].create({
            'profile_id': self.alice_profile.id,
            'name': 'Circle Feed',
            'type_id': circle_type.id,
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
            'category_id': self.env.ref('social_governance.category_other').id,
            'voting_closes_at': fields.Datetime.now() + datetime.timedelta(days=7),
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
            'category_id': self.env.ref('social_governance.category_other').id,
            'voting_closes_at': fields.Datetime.now() + datetime.timedelta(days=7),
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
        # Chaque type d'élément a ses propres ids : la clé est (type, id).
        ids_p1 = [(i['item_type'], i['id']) for i in result_p1['items']]
        ids_p2 = [(i['item_type'], i['id']) for i in result_p2['items']]
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

    # ── RSVP / event_registration ─────────────────────────────────────────────

    def _make_event(self, organizer, days_from_now=7, name='Événement Test Feed'):
        now = datetime.datetime.now()
        return self.env['event.event'].with_user(organizer).create({
            'name': name,
            'date_begin': now + datetime.timedelta(days=days_from_now),
            'date_end': now + datetime.timedelta(days=days_from_now, hours=3),
            'organizer_user_id': organizer.id,
            'social_visibility': 'members',
        })

    def _register(self, event, user):
        return self.env['event.registration'].sudo().create({
            'event_id': event.id,
            'partner_id': user.partner_id.id,
            'state': 'open',
        })

    def _connect(self, user_a, user_b):
        self.env['club_social_profile.connection'].sudo().create({
            'user_id': user_a.id,
            'connected_user_id': user_b.id,
            'connection_type': 'friend',
            'state': 'accepted',
        })

    def test_rsvp_from_connection_in_feed(self):
        """L'inscription d'une connexion doit apparaître dans le feed."""
        self._connect(self.alice, self.bob)
        event = self._make_event(self.alice)
        reg = self._register(event, self.bob)
        result = self.Feed.with_user(self.alice).get_feed(types=['event_registration'])
        ids = [i['id'] for i in result['items'] if i['item_type'] == 'event_registration']
        self.assertIn(reg.id, ids)

    def test_rsvp_from_stranger_excluded(self):
        """L'inscription d'un non-connexion ne doit pas apparaître."""
        event = self._make_event(self.alice)
        self._register(event, self.carol)
        result = self.Feed.with_user(self.alice).get_feed(types=['event_registration'])
        registrant_names = [i['registrant_name'] for i in result['items']
                            if i['item_type'] == 'event_registration']
        self.assertNotIn(self.carol.name, registrant_names)

    def test_rsvp_cancelled_excluded(self):
        """Une inscription annulée (state=cancel) ne doit pas apparaître."""
        self._connect(self.alice, self.bob)
        event = self._make_event(self.alice)
        reg = self._register(event, self.bob)
        reg.sudo().write({'state': 'cancel'})
        result = self.Feed.with_user(self.alice).get_feed(types=['event_registration'])
        ids = [i['id'] for i in result['items'] if i['item_type'] == 'event_registration']
        self.assertNotIn(reg.id, ids)

    def test_rsvp_no_connections_returns_empty(self):
        """Sans connexions, le type event_registration retourne une liste vide."""
        event = self._make_event(self.alice)
        self._register(event, self.carol)
        result = self.Feed.with_user(self.carol).get_feed(types=['event_registration'])
        self.assertEqual(result['items'], [])

    def test_rsvp_item_structure(self):
        """Un item event_registration doit avoir tous les champs attendus."""
        self._connect(self.alice, self.bob)
        event = self._make_event(self.alice, name='Soirée Structure')
        reg = self._register(event, self.bob)
        result = self.Feed.with_user(self.alice).get_feed(types=['event_registration'])
        items = [i for i in result['items'] if i['item_type'] == 'event_registration'
                 and i['id'] == reg.id]
        self.assertEqual(len(items), 1)
        item = items[0]
        self.assertEqual(item['registrant_name'], self.bob.name)
        self.assertEqual(item['event_id'], event.id)
        self.assertEqual(item['event_name'], 'Soirée Structure')
        self.assertIn('event_date_begin', item)
        self.assertIn('timestamp', item)

    def test_event_item_has_attendee_count(self):
        """Un item event doit inclure le nombre d'inscrits confirmés."""
        event = self._make_event(self.alice, name='Événement Compteur')
        self._register(event, self.bob)
        self._register(event, self.carol)
        result = self.Feed.with_user(self.alice).get_feed(types=['event'])
        items = [i for i in result['items']
                 if i['item_type'] == 'event' and i['id'] == event.id]
        self.assertEqual(len(items), 1)
        self.assertGreaterEqual(items[0]['attendee_count'], 2)

    def test_event_item_connection_attendee_names(self):
        """Un item event doit lister les noms des connexions inscrites (max 3)."""
        self._connect(self.alice, self.bob)
        event = self._make_event(self.alice, name='Événement Connexions')
        self._register(event, self.bob)
        result = self.Feed.with_user(self.alice).get_feed(types=['event'])
        items = [i for i in result['items']
                 if i['item_type'] == 'event' and i['id'] == event.id]
        self.assertEqual(len(items), 1)
        self.assertIn(self.bob.name, items[0]['connection_attendee_names'])

    def test_event_item_non_connection_not_in_connection_names(self):
        """Les inscrits non-connexion ne doivent pas apparaître dans connection_attendee_names."""
        event = self._make_event(self.alice, name='Événement Carol')
        self._register(event, self.carol)
        result = self.Feed.with_user(self.alice).get_feed(types=['event'])
        items = [i for i in result['items']
                 if i['item_type'] == 'event' and i['id'] == event.id]
        if items:
            self.assertNotIn(self.carol.name, items[0]['connection_attendee_names'])

    def test_rsvp_blocked_user_excluded(self):
        """L'inscription d'un utilisateur bloqué ne doit pas apparaître."""
        self._connect(self.alice, self.bob)
        event = self._make_event(self.alice, name='Événement Bloqué')
        reg = self._register(event, self.bob)
        self.env['social_safety.block'].with_user(self.alice).block_user(self.bob)
        try:
            result = self.Feed.with_user(self.alice).get_feed(types=['event_registration'])
            ids = [i['id'] for i in result['items'] if i['item_type'] == 'event_registration']
            self.assertNotIn(reg.id, ids)
        finally:
            self.env['social_safety.block'].with_user(self.alice).unblock_user(self.bob)

    def test_rsvp_in_full_feed(self):
        """Le type event_registration est inclus dans le feed complet (sans filtre)."""
        self._connect(self.alice, self.bob)
        event = self._make_event(self.alice, name='Événement Feed Complet')
        reg = self._register(event, self.bob)
        result = self.Feed.with_user(self.alice).get_feed(limit=100)
        types_present = {i['item_type'] for i in result['items']}
        self.assertIn('event_registration', types_present)

    # ── Gallery ───────────────────────────────────────────────────────────────

    def _make_approved_photo(self, name='Photo Feed'):
        import base64
        tiny_png = (
            b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01'
            b'\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00'
            b'\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82'
        )
        gallery = self.env['social_gallery.gallery'].sudo().create({
            'name': 'Galerie Feed Test',
            'owner_id': self.alice.id,
            'visibility': 'members',
        })
        photo = self.env['social_gallery.photo'].sudo().create({
            'gallery_id': gallery.id,
            'name': name,
            'image_1920': base64.b64encode(tiny_png).decode('ascii'),
            'submitted_by_id': self.alice.id,
            'state': 'approved',
            'moderation_date': datetime.datetime.now(),
        })
        return gallery, photo

    def test_gallery_photo_appears_in_feed(self):
        """Une photo approuvée d'une galerie members doit apparaître dans le feed."""
        gallery, photo = self._make_approved_photo()
        result = self.Feed.with_user(self.bob).get_feed(types=['gallery'])
        ids = [i['id'] for i in result['items'] if i['item_type'] == 'gallery']
        self.assertIn(photo.id, ids)

    def test_gallery_pending_photo_excluded(self):
        """Une photo en attente ne doit pas apparaître dans le feed."""
        gallery = self.env['social_gallery.gallery'].sudo().create({
            'name': 'Galerie Feed Pending',
            'owner_id': self.alice.id,
            'visibility': 'members',
        })
        photo = self.env['social_gallery.photo'].sudo().create({
            'gallery_id': gallery.id,
            'submitted_by_id': self.alice.id,
            'state': 'pending',
        })
        result = self.Feed.with_user(self.bob).get_feed(types=['gallery'])
        ids = [i['id'] for i in result['items'] if i['item_type'] == 'gallery']
        self.assertNotIn(photo.id, ids)

    def test_gallery_connections_gallery_excluded(self):
        """Les photos d'une galerie restreinte aux connexions ne doivent pas apparaître pour un non-connecté."""
        gallery = self.env['social_gallery.gallery'].sudo().create({
            'name': 'Galerie Feed Connexions',
            'owner_id': self.alice.id,
            'visibility': 'connections',
        })
        photo = self.env['social_gallery.photo'].sudo().create({
            'gallery_id': gallery.id,
            'submitted_by_id': self.alice.id,
            'state': 'approved',
        })
        result = self.Feed.with_user(self.bob).get_feed(types=['gallery'])
        ids = [i['id'] for i in result['items'] if i['item_type'] == 'gallery']
        self.assertNotIn(photo.id, ids)

    def test_gallery_item_structure(self):
        """Un item gallery doit avoir les champs attendus."""
        gallery, photo = self._make_approved_photo(name='Photo Structure')
        result = self.Feed.with_user(self.bob).get_feed(types=['gallery'])
        item = next((i for i in result['items']
                     if i['item_type'] == 'gallery' and i['id'] == photo.id), None)
        self.assertIsNotNone(item)
        for key in ('item_type', 'id', 'timestamp', 'gallery_id', 'gallery_name',
                    'photo_name', 'submitted_by_id', 'submitted_by_name'):
            self.assertIn(key, item)
        self.assertEqual(item['gallery_id'], gallery.id)

    # ── _parse_ts ─────────────────────────────────────────────────────────────

    def test_parse_ts_none_returns_none(self):
        from odoo.addons.social_feed.models.feed_service import _parse_ts
        self.assertIsNone(_parse_ts(None))

    def test_parse_ts_invalid_returns_none(self):
        from odoo.addons.social_feed.models.feed_service import _parse_ts
        self.assertIsNone(_parse_ts('not-a-date'))

    def test_parse_ts_naive_gets_utc(self):
        from odoo.addons.social_feed.models.feed_service import _parse_ts
        result = _parse_ts('2024-01-15T10:00:00')
        self.assertIsNotNone(result.tzinfo)

    def test_parse_ts_aware_preserved(self):
        from odoo.addons.social_feed.models.feed_service import _parse_ts
        result = _parse_ts('2024-01-15T10:00:00+05:00')
        self.assertIsNotNone(result)
        self.assertIsNotNone(result.tzinfo)

    # ── Service metadata ──────────────────────────────────────────────────────

    def test_get_feed_types_contains_expected(self):
        types = self.Feed.with_user(self.alice)._get_feed_types()
        for t in ('post', 'story', 'event', 'event_registration', 'proposal', 'gallery'):
            self.assertIn(t, types)

    def test_get_feed_dispatch_keys(self):
        dispatch = self.Feed.with_user(self.alice)._get_feed_dispatch()
        for t in ('post', 'story', 'event', 'event_registration', 'proposal', 'gallery'):
            self.assertIn(t, dispatch)
            self.assertTrue(callable(dispatch[t]))

    def test_post_item_html_stripped(self):
        """_post_item doit retourner un excerpt sans balises HTML."""
        post = self._make_post(self.alice, content='<b>texte</b> <em>important</em>')
        result = self.Feed.with_user(self.alice).get_feed(types=['post'])
        item = next((i for i in result['items']
                     if i['item_type'] == 'post' and i['id'] == post.id), None)
        self.assertIsNotNone(item)
        self.assertNotIn('<', item['content_excerpt'])
        self.assertNotIn('>', item['content_excerpt'])


@tagged('social_feed', 'feed', 'post_install', '-at_install')
class TestSocialFeedHttp(HttpCase):

    def test_feed_unauthenticated_redirects(self):
        resp = self.url_open('/social/api/feed', allow_redirects=False)
        self.assertIn(resp.status_code, (302, 303))

    def test_feed_authenticated_returns_json(self):
        self.authenticate('admin', 'admin')
        resp = self.url_open('/social/api/feed')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()['data']
        self.assertIn('items', data)
        self.assertIn('has_more', data)

    def test_feed_type_filter(self):
        self.authenticate('admin', 'admin')
        resp = self.url_open('/social/api/feed?types=post')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()['data']
        for item in data['items']:
            self.assertEqual(item['item_type'], 'post')

    def test_feed_sort_relevance(self):
        self.authenticate('admin', 'admin')
        resp = self.url_open('/social/api/feed?sort=relevance&limit=5')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()['data']
        self.assertIn('items', data)

    def test_feed_sort_invalid_defaults_to_recent(self):
        self.authenticate('admin', 'admin')
        resp = self.url_open('/social/api/feed?sort=invalid_sort')
        self.assertEqual(resp.status_code, 200)

    def test_feed_limit_param(self):
        self.authenticate('admin', 'admin')
        resp = self.url_open('/social/api/feed?limit=3')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()['data']
        self.assertLessEqual(len(data['items']), 3)
