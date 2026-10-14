import json

from odoo.exceptions import AccessError, UserError
from odoo.tests import HttpCase, new_test_user, tagged

API = '/api/social/v1'


@tagged('post_install', '-at_install')
class TestRelation(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.admin = cls.env.ref('base.user_admin')
        cls.a, cls.b, cls.c, cls.d = (cls._make_member(f'{n}.relation@example.com') for n in 'abcd')
        cls.Relation = cls.env['social_relation.relation']
        cls.partner_type = cls.env.ref('social_circles.rel_type_partner')

    @classmethod
    def _make_member(cls, login):
        user = new_test_user(cls.env, login=login, groups='base.group_portal')
        cls.env['club_social_profile.profile'].sudo().get_or_create_for_user(user)
        cls.env['social_reputation.vouching'].with_user(cls.admin).sudo().vouch_for(user)
        membership = cls.env['club_membership.membership'].sudo().create({
            'partner_id': user.partner_id.id,
            'membership_type_id': cls.env.ref('club_membership.membership_type_regular').id,
        })
        membership.action_activate()
        return user

    def _couple(self, first, second, name="Couple"):
        relation = self.Relation.with_user(first).action_create_relation(name)
        relation.with_user(first).action_invite(second)
        relation.with_user(second).action_accept()
        return relation

    def _pair(self, x, y):
        return self.env['res.partner.relation'].sudo().search([
            ('type_id', '=', self.partner_type.id),
            '|',
            '&', ('left_partner_id', '=', x.partner_id.id), ('right_partner_id', '=', y.partner_id.id),
            '&', ('left_partner_id', '=', y.partner_id.id), ('right_partner_id', '=', x.partner_id.id),
        ])

    def _member(self, relation, user):
        return relation.sudo().member_ids.filtered(lambda m: m.user_id == user)

    # ── Modèle ───────────────────────────────────────────────────────────────

    def test_couple_links_both_accounts(self):
        relation = self.Relation.with_user(self.a).action_create_relation("A et B")
        self.assertEqual(relation.sudo().state, 'forming')
        relation.with_user(self.a).action_invite(self.b)
        self.assertEqual(self._member(relation, self.b).state, 'invited', "seul membre : invitation directe")
        relation.with_user(self.b).action_accept()

        relation = relation.sudo()
        self.assertEqual(relation.state, 'active')
        self.assertTrue(self._pair(self.a, self.b).active)
        self.assertEqual(relation.channel_id.channel_member_ids.partner_id, (self.a | self.b).partner_id)
        # Le lien à deux alimente le cercle « Partenaires » existant.
        circle = self.env['club_social_profile.profile'].sudo().search([('user_id', '=', self.a.id)]).circle_ids.filtered(
            lambda c: c.type_id == self.partner_type.circle_type_id)
        self.assertIn(self.b, circle.member_ids)

    def test_new_member_needs_every_member(self):
        relation = self._couple(self.a, self.b)
        relation.with_user(self.a).action_invite(self.c)
        proposal = self._member(relation, self.c)
        self.assertEqual(proposal.state, 'proposed', "B doit d'abord accepter l'arrivée de C")
        with self.assertRaises(AccessError):
            relation.with_user(self.c).action_accept()
        proposal.with_user(self.b).action_approve()
        self.assertEqual(proposal.state, 'invited')
        relation.with_user(self.c).action_accept()

        self.assertEqual(relation.sudo().member_count, 3)
        for x, y in ((self.a, self.b), (self.a, self.c), (self.b, self.c)):
            self.assertTrue(self._pair(x, y).active)
        self.assertEqual(len(relation.sudo().channel_id.channel_member_ids), 3)

    def test_rejected_proposal(self):
        relation = self._couple(self.a, self.b)
        relation.with_user(self.a).action_invite(self.c)
        self._member(relation, self.c).with_user(self.b).action_reject()
        self.assertEqual(self._member(relation, self.c).state, 'declined')

    def test_visible_only_if_everyone_agrees(self):
        relation = self._couple(self.a, self.b)
        relation.with_user(self.a).action_set_share(True)
        self.assertFalse(relation.sudo().is_visible)
        relation.with_user(self.b).action_set_share(True)
        self.assertTrue(relation.sudo().is_visible)
        self.assertTrue(relation._visible_to(self.d))
        # Quelqu'un qui arrive ne rend pas la relation visible sans son accord.
        relation.with_user(self.a).action_invite(self.c)
        self._member(relation, self.c).with_user(self.b).action_approve()
        relation.with_user(self.c).action_accept()
        self.assertFalse(relation.sudo().is_visible)
        # Un blocage entre D et un membre cache la relation à D.
        relation.with_user(self.c).action_set_share(True)
        self.env['social_safety.block'].sudo().create({'blocker_id': self.c.id, 'blocked_id': self.d.id})
        self.assertFalse(relation._visible_to(self.d))

    def test_member_of_several_relations(self):
        first = self._couple(self.a, self.b, "Premier")
        second = self._couple(self.a, self.c, "Second")
        third = self._couple(self.b, self.a, "Troisième")  # même paire, autre relation
        self.assertEqual(len(self._pair(self.a, self.b)), 1, "le lien existant est réutilisé")
        first.with_user(self.b).action_leave()
        self.assertEqual(first.sudo().state, 'dissolved')
        self.assertTrue(self._pair(self.a, self.b).active, "toujours utilisé par la troisième relation")
        third.with_user(self.a).action_leave()
        self.assertFalse(self._pair(self.a, self.b).active)
        self.assertTrue(self._pair(self.a, self.c).active)
        self.assertEqual(second.sudo().state, 'active')

    def test_leaving_trouple(self):
        relation = self._couple(self.a, self.b)
        relation.with_user(self.a).action_invite(self.c)
        self._member(relation, self.c).with_user(self.b).action_approve()
        relation.with_user(self.c).action_accept()
        relation.with_user(self.c).action_leave()
        relation = relation.sudo()
        self.assertEqual(relation.state, 'active')
        self.assertFalse(self._pair(self.a, self.c).active)
        self.assertTrue(self._pair(self.a, self.b).active)
        self.assertNotIn(self.c.partner_id, relation.channel_id.channel_member_ids.partner_id)

    def test_outsiders(self):
        relation = self._couple(self.a, self.b)
        self.assertFalse(self.Relation.with_user(self.d).search([('id', '=', relation.id)]))
        with self.assertRaises(AccessError):
            relation.with_user(self.d).action_invite(self.c)
        outsider = new_test_user(self.env, login='hors.reseau@example.com', groups='base.group_portal')
        with self.assertRaises(UserError):
            relation.with_user(self.a).action_invite(outsider)
        self.env['social_safety.block'].sudo().create({'blocker_id': self.d.id, 'blocked_id': self.b.id})
        with self.assertRaises(UserError):
            relation.with_user(self.a).action_invite(self.d)

    # ── API ──────────────────────────────────────────────────────────────────

    def _key(self, user):
        key, _exp = self.env['res.users.apikeys'].with_user(user)._social_mobile_generate('test')
        return key

    def call(self, method, path, user, body=None):
        headers = {'Content-Type': 'application/json', 'Authorization': f'Bearer {self._key(user)}'}
        return self.url_open(API + path, data=json.dumps(body) if body is not None else None, headers=headers, method=method)

    def test_api_flow(self):
        res = self.call('POST', '/relations', self.a, {'name': "Trouple"})
        self.assertEqual(res.status_code, 200, res.text)
        rid = res.json()['relation']['id']
        self.assertEqual(self.call('POST', f'/relations/{rid}/invite', self.a, {'user_id': self.b.id}).status_code, 200)
        self.assertEqual(self.call('POST', f'/relations/{rid}/accept', self.b).json()['relation']['state'], 'active')

        payload = self.call('POST', f'/relations/{rid}/invite', self.a, {'user_id': self.c.id}).json()['relation']
        proposal = next(m for m in payload['members'] if m['user_id'] == self.c.id)
        self.assertEqual(proposal['state'], 'proposed')
        self.call('POST', f"/relations/{rid}/members/{proposal['member_id']}/approve", self.b)
        self.assertEqual(self.call('POST', f'/relations/{rid}/accept', self.c).status_code, 200)

        listed = self.call('GET', '/relations', self.c).json()['relations']
        self.assertEqual([r['id'] for r in listed], [rid])
        # Relation discrète : invisible pour D, y compris sur le profil d'un membre.
        self.assertEqual(self.call('GET', f'/relations/{rid}', self.d).status_code, 404)
        self.assertEqual(self.call('GET', f'/users/{self.a.id}/relations', self.d).json()['relations'], [])
        for user in (self.a, self.b, self.c):
            self.call('POST', f'/relations/{rid}/share', user, {'share': True})
        seen = self.call('GET', f'/relations/{rid}', self.d).json()['relation']
        self.assertEqual(len(seen['members']), 3)
        self.assertIsNone(seen['members'][0]['share_publicly'], "les réglages des membres restent privés")
        self.assertEqual(self.call('GET', f'/users/{self.a.id}/relations', self.d).json()['relations'][0]['id'], rid)
        # Un non-membre ne peut rien modifier.
        self.assertEqual(self.call('POST', f'/relations/{rid}/invite', self.d, {'user_id': self.d.id}).status_code, 404)
