import datetime
import json

from odoo import fields
from odoo.tests import HttpCase, new_test_user, tagged

from odoo.addons.social_nearby.models.position import AREA_DEG, area, distance_km, snap

API = '/api/social/v1'
MONTREAL = (45.50170, -73.56730)
QUEBEC = (46.81390, -71.20800)


def offset(point, north_m=0.0, east_m=0.0):
    lat, lon = point
    return lat + north_m / 111_000, lon + east_m / (111_000 * 0.70)


@tagged('post_install', '-at_install')
class TestNearby(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.admin = cls.env.ref('base.user_admin')
        cls.Position = cls.env['social_nearby.position']
        cls.viewer = cls._make_member('viewer.nearby@example.com')

    @classmethod
    def _make_member(cls, login, **profile_vals):
        user = new_test_user(cls.env, login=login, groups='base.group_portal')
        profile = cls.env['club_social_profile.profile'].sudo().get_or_create_for_user(user)
        profile.write(dict({'onboarding_done': True, 'birth_year': 1985, 'gender': 'femme'}, **profile_vals))
        cls.env['social_reputation.vouching'].with_user(cls.admin).sudo().vouch_for(user)
        membership = cls.env['club_membership.membership'].sudo().create({
            'partner_id': user.partner_id.id,
            'membership_type_id': cls.env.ref('club_membership.membership_type_regular').id,
        })
        membership.action_activate()
        return user

    def at(self, user, point):
        self.Position.with_user(user)._api_report(*point)

    def grid(self, **kw):
        return self.Position._api_grid(self.viewer, **kw)

    def names(self, grid):
        return {p['user_id'] for p in grid['people']}

    # ── Position ─────────────────────────────────────────────────────────────

    def test_exact_position_is_never_stored(self):
        self.at(self.viewer, MONTREAL)
        stored = self.Position.sudo().search([('user_id', '=', self.viewer.id)])
        self.assertNotAlmostEqual(stored.cell_lat, MONTREAL[0], places=5)
        # Deux points à 100 m l'un de l'autre, dans la même case, donnent exactement la même valeur.
        self.assertEqual(snap(45.50010, -73.56510), snap(45.50090, -73.56510))
        self.assertLess(distance_km(stored.cell_lat, stored.cell_lon, *MONTREAL), 0.5)
        self.at(self.viewer, QUEBEC)
        self.assertEqual(self.Position.sudo().search_count([('user_id', '=', self.viewer.id)]), 1, "aucun historique")

    def test_grid_requires_own_position(self):
        self.assertIsNone(self.grid())

    # ── Grille ───────────────────────────────────────────────────────────────

    def test_grid_filters_and_buckets(self):
        near = self._make_member('proche@example.com')
        far = self._make_member('quebec@example.com')
        blocked = self._make_member('bloque@example.com')
        unfinished = self._make_member('pas.fini@example.com', onboarding_done=False)
        connections_only = self._make_member('connexions@example.com', visibility='connections')
        private = self._make_member('prive@example.com', detailed_visibility='private')
        banned = self._make_member('banni@example.com')
        self.env['club_social_profile.profile'].sudo().search([('user_id', '=', banned.id)]).is_shadow_banned = True
        self.env['social_safety.block'].sudo().create({'blocker_id': blocked.id, 'blocked_id': self.viewer.id})

        self.at(self.viewer, MONTREAL)
        for user in (near, blocked, unfinished, connections_only, private, banned):
            self.at(user, offset(MONTREAL, north_m=300))
        self.at(far, QUEBEC)

        grid = self.grid()
        self.assertEqual(self.names(grid), {near.id, private.id})
        tile = next(p for p in grid['people'] if p['user_id'] == near.id)
        self.assertEqual(tile['distance'], "< 1 km")
        self.assertEqual(tile['last_seen'], 'now')
        self.assertEqual(tile['age'], fields.Date.today().year - 1985)
        hidden = next(p for p in grid['people'] if p['user_id'] == private.id)
        self.assertFalse(hidden['detailed'])
        self.assertNotIn('age', hidden, "infos détaillées cachées par le profil")
        self.assertNotIn('quebec', json.dumps(grid))

        # Québec est à environ 233 km : hors du rayon maximal (200 km).
        self.assertGreater(distance_km(*MONTREAL, *QUEBEC), 200)
        self.assertNotIn(far.id, self.names(self.grid(radius_km=500)))

    def test_sorted_by_distance_and_stale_dropped(self):
        first = self._make_member('a1@example.com')
        second = self._make_member('a2@example.com')
        stale = self._make_member('a3@example.com')
        self.at(self.viewer, MONTREAL)
        self.at(first, offset(MONTREAL, east_m=1500))
        self.at(second, offset(MONTREAL, east_m=7000))
        self.at(stale, offset(MONTREAL, east_m=500))
        self.Position.sudo().search([('user_id', '=', stale.id)]).seen_at = fields.Datetime.now() - datetime.timedelta(days=8)
        grid = self.grid()
        self.assertEqual([p['user_id'] for p in grid['people']], [first.id, second.id])
        self.assertEqual(grid['people'][1]['distance'], "5–10 km")
        self.Position._cron_purge()
        self.assertFalse(self.Position.sudo().search([('user_id', '=', stale.id)]))

    def test_visible_relation_tile(self):
        a = self._make_member('rel.a@example.com')
        b = self._make_member('rel.b@example.com')
        Relation = self.env['social_relation.relation']
        relation = Relation.with_user(a).action_create_relation("A et B")
        relation.with_user(a).action_invite(b)
        relation.with_user(b).action_accept()
        self.at(self.viewer, MONTREAL)
        self.at(a, offset(MONTREAL, north_m=3000))
        self.assertEqual(self.grid()['relations'], [], "relation discrète : pas de tuile")
        relation.with_user(a).action_set_share(True)
        relation.with_user(b).action_set_share(True)
        tiles = self.grid()['relations']
        self.assertEqual([t['id'] for t in tiles], [relation.id])
        self.assertEqual(tiles[0]['distance'], "2–5 km")

    # ── API ──────────────────────────────────────────────────────────────────

    def call(self, method, path, user, body=None):
        key, _exp = self.env['res.users.apikeys'].with_user(user)._social_mobile_generate('test')
        headers = {'Content-Type': 'application/json', 'Authorization': f'Bearer {key}'}
        return self.url_open(API + path, data=json.dumps(body) if body is not None else None, headers=headers, method=method)

    def test_api(self):
        near = self._make_member('api.proche@example.com')
        self.assertEqual(self.call('GET', '/nearby', self.viewer).status_code, 409)
        self.assertEqual(self.call('POST', '/position', self.viewer, {'latitude': 200, 'longitude': 0}).status_code, 400)
        self.call('POST', '/position', self.viewer, {'latitude': MONTREAL[0], 'longitude': MONTREAL[1]})
        self.call('POST', '/position', near, dict(zip(('latitude', 'longitude'), offset(MONTREAL, north_m=200))))
        res = self.call('GET', '/nearby?radius_km=10', self.viewer)
        self.assertEqual(res.status_code, 200, res.text)
        self.assertEqual([p['user_id'] for p in res.json()['people']], [near.id])
        self.assertEqual(self.call('DELETE', '/position', near).json()['shared'], False)
        self.assertEqual(self.call('GET', '/nearby', self.viewer).json()['people'], [])

        outsider = new_test_user(self.env, login='hors.grille@example.com', groups='base.group_portal')
        self.assertEqual(self.call('POST', '/position', outsider, {'latitude': 45.5, 'longitude': -73.5}).status_code, 403)
        self.assertEqual(self.call('GET', '/nearby', outsider).status_code, 403)

    # ── Je veux rencontrer ───────────────────────────────────────────────────

    def test_meet_mode(self):
        near = self._make_member('rencontre.proche@example.com')
        far = self._make_member('rencontre.loin@example.com')
        self.assertEqual(self.call('POST', '/meet', near, {'active': True}).status_code, 409, "sans position")
        self.at(self.viewer, MONTREAL)
        self.at(far, offset(MONTREAL, north_m=8000))
        self.at(near, offset(MONTREAL, north_m=200))
        self.assertEqual(self.call('POST', '/meet', far, {'active': 'oui'}).status_code, 400)

        for hours in (0, 13, 2.5, '3'):
            self.assertEqual(self.call('POST', '/meet', far, {'active': True, 'hours': hours}).status_code, 400, hours)
        res = self.call('POST', '/meet', far, {'active': True})
        until = fields.Datetime.to_datetime(res.json()['meet_until'][:19].replace('T', ' '))
        self.assertAlmostEqual((until - fields.Datetime.now()).total_seconds(), 3 * 3600, delta=60, msg="3 h par défaut")
        res = self.call('POST', '/meet', far, {'active': True, 'hours': 6})
        self.assertEqual(res.status_code, 200, res.text)
        until = fields.Datetime.to_datetime(res.json()['meet_until'][:19].replace('T', ' '))
        self.assertAlmostEqual((until - fields.Datetime.now()).total_seconds(), 6 * 3600, delta=60)

        # Qui veut rencontrer passe en tête, même plus loin ; son activité reste la vraie.
        position = self.Position.sudo().search([('user_id', '=', far.id)])
        position.seen_at = fields.Datetime.now() - datetime.timedelta(hours=2)
        people = self.grid()['people']
        self.assertEqual([p['user_id'] for p in people], [far.id, near.id])
        self.assertEqual((people[0]['meet'], people[0]['last_seen']), (True, 'today'))
        self.assertFalse(people[1]['meet'])
        self.assertEqual(self.call('GET', '/nearby', far).json()['meet_until'][:16], res.json()['meet_until'][:16])

        # Échu après trois heures : plus signalé ni en tête.
        position.meet_until = fields.Datetime.now() - datetime.timedelta(seconds=1)
        people = self.grid()['people']
        self.assertEqual([p['user_id'] for p in people], [near.id, far.id])
        self.assertEqual((people[1]['meet'], people[1]['last_seen']), (False, 'today'))
        self.assertIsNone(self.grid()['meet_until'])

        self.call('POST', '/meet', far, {'active': True})
        self.assertIsNone(self.call('POST', '/meet', far, {'active': False}).json()['meet_until'])
        self.assertFalse(position.meet_until)

    def test_map_area_is_coarse(self):
        """Carte : chacun est montré dans une zone d'environ 2 km, jamais dans sa case de 550 m."""
        a = self._make_member('carte.a@example.com')
        b = self._make_member('carte.b@example.com')
        self.at(self.viewer, MONTREAL)
        # Deux cases de 550 m différentes, dans la même zone de 0,02°.
        base = snap(*MONTREAL, AREA_DEG)
        self.at(a, offset(base, north_m=-600, east_m=-600))
        self.at(b, offset(base, north_m=600, east_m=600))
        tiles = {p['user_id']: p for p in self.grid()['people']}
        cell_a = self.Position.sudo().search([('user_id', '=', a.id)])
        cell_b = self.Position.sudo().search([('user_id', '=', b.id)])
        self.assertNotEqual((cell_a.cell_lat, cell_a.cell_lon), (cell_b.cell_lat, cell_b.cell_lon))
        self.assertEqual(tiles[a.id]['area'], tiles[b.id]['area'], "même quartier, même zone")
        self.assertEqual(tiles[a.id]['area'], {'latitude': base[0], 'longitude': base[1], 'radius_m': 1500})
        self.assertEqual(area(cell_a.cell_lat, cell_a.cell_lon), tiles[a.id]['area'])
        self.assertNotIn(str(cell_a.cell_lat), json.dumps(tiles[a.id]), "la case ne sort jamais")
