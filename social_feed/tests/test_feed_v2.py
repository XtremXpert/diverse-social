from datetime import timedelta

from odoo import fields
from odoo.tests import HttpCase, TransactionCase, tagged
from odoo.exceptions import ValidationError


def _make_user(env, login):
    user = env['res.users'].create({
        'name': login.capitalize(),
        'login': login,
        'email': f'{login}@feedv2.test',
        'password': 'Test1234!',
        'group_ids': [(4, env.ref('base.group_user').id),
                      (4, env.ref('social_base.group_social_user').id)],
    })
    env['club_social_profile.profile'].sudo().get_or_create_for_user(user)
    return user


@tagged('social_feed', 'feed_v2', 'post_install', '-at_install')
class TestUserPreference(TransactionCase):

    def setUp(self):
        super().setUp()
        self.user = _make_user(self.env, 'fv2_pref_user')
        self.Pref = self.env['social_feed.user_preference']

    def test_set_boost_creates_and_clamps(self):
        # In-range: kept as-is
        p = self.Pref.set_boost(self.user.id, 'post', 2.5)
        self.assertAlmostEqual(p.boost_factor, 2.5)
        # Above max: clamped down
        p = self.Pref.set_boost(self.user.id, 'post', 999)
        self.assertAlmostEqual(p.boost_factor, 5.0)
        # Below min: clamped up
        p = self.Pref.set_boost(self.user.id, 'post', -1)
        self.assertAlmostEqual(p.boost_factor, 0.1)

    def test_set_boost_is_idempotent_per_type(self):
        a = self.Pref.set_boost(self.user.id, 'event', 1.5)
        b = self.Pref.set_boost(self.user.id, 'event', 2.0)
        # Same row updated, not a second one created
        self.assertEqual(a.id, b.id)
        self.assertAlmostEqual(b.boost_factor, 2.0)
        cnt = self.Pref.search_count([('user_id', '=', self.user.id), ('item_type', '=', 'event')])
        self.assertEqual(cnt, 1)

    def test_boosts_for_user_sparse(self):
        self.Pref.set_boost(self.user.id, 'post', 2.0)
        self.Pref.set_boost(self.user.id, 'event', 0.5)
        boosts = self.Pref.boosts_for_user(self.user.id)
        self.assertEqual(boosts, {'post': 2.0, 'event': 0.5})

    def test_direct_create_out_of_range_raises(self):
        with self.assertRaises(ValidationError):
            self.Pref.create({
                'user_id': self.user.id, 'item_type': 'post', 'boost_factor': 100,
            })


@tagged('social_feed', 'feed_v2', 'post_install', '-at_install')
class TestReadMarker(TransactionCase):

    def setUp(self):
        super().setUp()
        self.user = _make_user(self.env, 'fv2_mark_user')
        self.Marker = self.env['social_feed.read_marker']

    def test_mark_read_is_idempotent(self):
        a = self.Marker.mark_read(self.user.id, 'post', 42)
        b = self.Marker.mark_read(self.user.id, 'post', 42)
        self.assertEqual(a.id, b.id)
        self.assertEqual(
            self.Marker.search_count([
                ('user_id', '=', self.user.id), ('item_type', '=', 'post'), ('item_id', '=', 42),
            ]),
            1,
        )

    def test_mark_unread_removes_row(self):
        self.Marker.mark_read(self.user.id, 'story', 7)
        self.Marker.mark_unread(self.user.id, 'story', 7)
        self.assertFalse(self.Marker.search([
            ('user_id', '=', self.user.id),
            ('item_type', '=', 'story'),
            ('item_id', '=', 7),
        ]))

    def test_read_set_for_user_scoped_to_items(self):
        self.Marker.mark_read(self.user.id, 'post', 1)
        self.Marker.mark_read(self.user.id, 'post', 2)
        self.Marker.mark_read(self.user.id, 'story', 1)
        # Different types with the same id must not collide
        result = self.Marker.read_set_for_user(self.user.id, items=[
            {'item_type': 'post', 'id': 1},
            {'item_type': 'post', 'id': 3},  # not marked
            {'item_type': 'story', 'id': 1},
        ])
        self.assertEqual(result, {('post', 1), ('story', 1)})

    def test_cron_cleanup_purges_old_markers(self):
        old = self.Marker.create({
            'user_id': self.user.id, 'item_type': 'post', 'item_id': 100,
        })
        # Backdate beyond retention window
        self.env.cr.execute(
            "UPDATE social_feed_read_marker SET read_at = %s WHERE id = %s",
            (fields.Datetime.now() - timedelta(days=45), old.id),
        )
        self.env.cr.flush()
        recent = self.Marker.create({
            'user_id': self.user.id, 'item_type': 'post', 'item_id': 101,
        })
        purged = self.Marker.cron_cleanup_old_markers()
        self.assertGreaterEqual(purged, 1)
        self.assertFalse(old.exists())
        self.assertTrue(recent.exists(), 'recent marker should be kept')


@tagged('social_feed', 'feed_v2', 'post_install', '-at_install')
class TestFeedScoringWithUserBoost(TransactionCase):

    def setUp(self):
        super().setUp()
        self.user = _make_user(self.env, 'fv2_score_user')
        self.Service = self.env['social_feed.service']

    def _score(self, item, user_boosts=None):
        ctx = {
            'user': self.user,
            'connection_user_ids': [],
            'user_boosts': user_boosts or {},
        }
        # Pick a stable 'now' to keep recency deterministic
        from datetime import datetime, timezone
        now = datetime(2026, 6, 1, tzinfo=timezone.utc)
        return self.Service._score_item(item, ctx, now, set())

    def test_boost_above_one_increases_score(self):
        item = {
            'item_type': 'post', 'timestamp': '2026-06-01T00:00:00',
            'like_count': 5, 'comment_count': 2, 'author_id': 1,
        }
        baseline = self._score(item)
        boosted = self._score(item, user_boosts={'post': 2.0})
        self.assertAlmostEqual(boosted, baseline * 2.0, places=4)

    def test_boost_below_one_decreases_score(self):
        item = {
            'item_type': 'event', 'timestamp': '2026-06-01T00:00:00',
            'date_begin': '2026-06-02T00:00:00', 'like_count': 0, 'author_id': 1,
        }
        baseline = self._score(item)
        damped = self._score(item, user_boosts={'event': 0.5})
        self.assertAlmostEqual(damped, baseline * 0.5, places=4)

    def test_other_types_unaffected(self):
        post = {
            'item_type': 'post', 'timestamp': '2026-06-01T00:00:00',
            'like_count': 1, 'author_id': 1,
        }
        baseline = self._score(post)
        with_event_boost = self._score(post, user_boosts={'event': 3.0})
        self.assertAlmostEqual(baseline, with_event_boost, places=4)
