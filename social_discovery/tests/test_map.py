import json

from odoo.tests import HttpCase, TransactionCase, tagged


def _make_social_user(env, login, *, moderator=False):
    group_user = env.ref('base.group_user')
    group_social = env.ref('social_base.group_social_user')
    groups = [(4, group_user.id), (4, group_social.id)]
    if moderator:
        groups.append((4, env.ref('social_base.group_social_moderator').id))
    user = env['res.users'].create({
        'name': login.capitalize(),
        'login': login,
        'email': f'{login}@map.test',
        'password': 'Test1234!',
        'group_ids': groups,
    })
    profile = env['club_social_profile.profile'].sudo().get_or_create_for_user(user)
    return user, profile


@tagged('social_discovery', 'map', 'post_install', '-at_install')
class TestMapJitter(TransactionCase):

    def setUp(self):
        super().setUp()
        self.user, self.profile = _make_social_user(self.env, 'jitter_alice')

    def test_jitter_zero_when_unlocated(self):
        self.assertEqual(self.profile.geo_lat_jitter, 0.0)
        self.assertEqual(self.profile.geo_lng_jitter, 0.0)

    def test_jitter_stable_across_recomputes(self):
        self.profile.write({'geo_lat': 45.5, 'geo_lng': -73.6})
        a_lat, a_lng = self.profile.geo_lat_jitter, self.profile.geo_lng_jitter
        # Force a recompute by re-writing the same source values.
        self.profile.write({'geo_lat': 45.5, 'geo_lng': -73.6})
        self.profile.invalidate_recordset()
        self.assertAlmostEqual(self.profile.geo_lat_jitter, a_lat, places=6)
        self.assertAlmostEqual(self.profile.geo_lng_jitter, a_lng, places=6)

    def test_jitter_within_3km(self):
        self.profile.write({'geo_lat': 45.5, 'geo_lng': -73.6})
        # Crude check: jitter offset should be under ~4km in any direction.
        # 0.04 deg latitude ≈ 4.5 km, generous upper bound for the 2-3 km radius.
        self.assertLess(abs(self.profile.geo_lat_jitter - 45.5), 0.04)
        self.assertLess(abs(self.profile.geo_lng_jitter - -73.6), 0.06)

    def test_jitter_different_for_different_profiles(self):
        _, other = _make_social_user(self.env, 'jitter_bob')
        self.profile.write({'geo_lat': 45.5, 'geo_lng': -73.6})
        other.write({'geo_lat': 45.5, 'geo_lng': -73.6})
        self.assertNotEqual(
            (self.profile.geo_lat_jitter, self.profile.geo_lng_jitter),
            (other.geo_lat_jitter, other.geo_lng_jitter),
        )


@tagged('social_discovery', 'map', 'post_install', '-at_install')
class TestGeoStatusReset(TransactionCase):

    def setUp(self):
        super().setUp()
        self.user, self.profile = _make_social_user(self.env, 'geostatus_alice')

    def test_write_city_resets_to_pending(self):
        self.profile.write({
            'city': 'Montréal',
            'geo_lat': 45.5, 'geo_lng': -73.6,
            'geo_status': 'done',
            'geo_geocoded_address': 'Old',
        })
        self.assertEqual(self.profile.geo_status, 'pending')
        self.assertEqual(self.profile.geo_lat, 0.0)
        self.assertFalse(self.profile.geo_geocoded_address)

    def test_write_unrelated_field_does_not_reset(self):
        self.profile.write({
            'city': 'Montréal',
            'geo_lat': 45.5, 'geo_lng': -73.6,
            'geo_status': 'done',
            'geo_geocoded_address': 'Montréal',
        })
        # Touch an unrelated field — geocoding state must persist.
        self.profile.write({'bio': 'Hello'})
        self.assertEqual(self.profile.geo_status, 'done')
        self.assertEqual(self.profile.geo_lat, 45.5)


@tagged('social_discovery', 'map', 'post_install', '-at_install')
class TestGeocoderCache(TransactionCase):

    def setUp(self):
        super().setUp()
        self.Cache = self.env['social_discovery.geo_cache']

    def test_normalize_lowercases_and_trims(self):
        self.assertEqual(self.Cache._normalize('  Montréal,  QC  '), 'montréal, qc')
        self.assertEqual(self.Cache._normalize(''), '')
        self.assertEqual(self.Cache._normalize(None), '')

    def test_cache_lookup_by_normalized_key(self):
        self.Cache.create({
            'address_key': self.Cache._normalize('Montréal, QC'),
            'lat': 45.5, 'lng': -73.6,
        })
        hit = self.Cache.search([
            ('address_key', '=', self.Cache._normalize('  montréal,  qc  ')),
        ], limit=1)
        self.assertTrue(hit)
        self.assertEqual(hit.lat, 45.5)


@tagged('social_discovery', 'map', 'map_http', 'post_install', '-at_install')
class TestMapEndpoint(HttpCase):

    def setUp(self):
        super().setUp()
        # Searcher: opted-in, will hit /members/map.json
        self.searcher_user, self.searcher_profile = _make_social_user(self.env, 'map_searcher')
        self.searcher_profile.write({'show_on_map': True})

        # Visible target in bbox
        self.alice_user, self.alice_profile = _make_social_user(self.env, 'map_alice')
        self.alice_profile.write({
            'show_on_map': True,
            'visibility': 'members',
            'geo_lat': 45.5, 'geo_lng': -73.6,
            'geo_status': 'done',
        })

        # Opt-out target — should never appear for a regular user
        self.bob_user, self.bob_profile = _make_social_user(self.env, 'map_bob')
        self.bob_profile.write({
            'show_on_map': False,
            'visibility': 'members',
            'geo_lat': 45.5, 'geo_lng': -73.6,
            'geo_status': 'done',
        })

        # Moderator
        self.mod_user, self.mod_profile = _make_social_user(
            self.env, 'map_moderator', moderator=True,
        )

    def _login_and_get_json(self, login):
        self.authenticate(login, 'Test1234!')
        resp = self.url_open('/members/map.json?bbox=44,-75,46,-72')
        self.assertEqual(resp.status_code, 200, resp.text)
        return json.loads(resp.content)

    def test_opt_out_user_gets_403(self):
        self.searcher_profile.write({'show_on_map': False})
        self.authenticate('map_searcher', 'Test1234!')
        resp = self.url_open('/members/map.json?bbox=44,-75,46,-72')
        self.assertEqual(resp.status_code, 403)

    def test_opted_in_user_sees_opted_in_targets(self):
        data = self._login_and_get_json('map_searcher')
        user_ids = [p['user_id'] for p in data['points']]
        self.assertIn(self.alice_user.id, user_ids)
        self.assertNotIn(self.bob_user.id, user_ids, 'opt-out profile leaked to a peer')

    def test_no_login_in_json_payload(self):
        # PII guardrail: login (email) must never appear in the public payload.
        data = self._login_and_get_json('map_searcher')
        for p in data['points']:
            self.assertNotIn('login', p, 'login (email) leaked to JSON')
            self.assertNotIn('@', p.get('name', ''))

    def test_moderator_sees_opted_out_profiles(self):
        data = self._login_and_get_json('map_moderator')
        user_ids = [p['user_id'] for p in data['points']]
        self.assertIn(self.alice_user.id, user_ids)
        self.assertIn(self.bob_user.id, user_ids, 'moderator missing opt-out profile')

    def test_bbox_filters_out_of_view_points(self):
        self.authenticate('map_searcher', 'Test1234!')
        # Africa-only bbox — nothing in Quebec should match
        resp = self.url_open('/members/map.json?bbox=-10,10,10,30')
        data = json.loads(resp.content)
        self.assertEqual(data['count'], 0)

    def test_returns_jittered_not_raw_coords(self):
        data = self._login_and_get_json('map_searcher')
        alice = next(p for p in data['points'] if p['user_id'] == self.alice_user.id)
        # Returned coord should differ from the raw 45.5/-73.6 (jitter applied)
        self.assertNotEqual((alice['lat'], alice['lng']), (45.5, -73.6))
