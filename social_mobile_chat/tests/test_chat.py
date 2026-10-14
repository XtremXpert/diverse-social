import json

from odoo.tests import HttpCase, new_test_user, tagged

API = '/api/social/v1'


@tagged('post_install', '-at_install')
class TestMobileChat(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.admin = cls.env.ref('base.user_admin')
        cls.a, cls.b, cls.c = (cls._make_member(f'{n}.chat@example.com') for n in 'abc')
        # A et B sont connectés : ils peuvent s'écrire. C n'a aucun lien avec A.
        Connection = cls.env['club_social_profile.connection'].sudo()
        Connection.create({'user_id': cls.a.id, 'connected_user_id': cls.b.id, 'state': 'accepted'})
        Connection.create({'user_id': cls.b.id, 'connected_user_id': cls.a.id, 'state': 'accepted'})

    @classmethod
    def _make_member(cls, login):
        user = new_test_user(cls.env, login=login, groups='base.group_portal')
        profile = cls.env['club_social_profile.profile'].sudo().get_or_create_for_user(user)
        profile.stealth_name = login.split('.')[0].upper()
        cls.env['social_reputation.vouching'].with_user(cls.admin).sudo().vouch_for(user)
        membership = cls.env['club_membership.membership'].sudo().create({
            'partner_id': user.partner_id.id,
            'membership_type_id': cls.env.ref('club_membership.membership_type_regular').id,
        })
        membership.action_activate()
        return user

    def call(self, method, path, user, body=None):
        key, _exp = self.env['res.users.apikeys'].with_user(user)._social_mobile_generate('test')
        headers = {'Content-Type': 'application/json', 'Authorization': f'Bearer {key}'}
        return self.url_open(API + path, data=json.dumps(body) if body is not None else None, headers=headers, method=method)

    def open_chat(self, user, other):
        return self.call('POST', '/chats', user, {'user_id': other.id})

    def test_private_conversation(self):
        res = self.open_chat(self.a, self.b)
        self.assertEqual(res.status_code, 200, res.text)
        chat = res.json()['chat']
        self.assertEqual(chat['kind'], 'chat')
        self.assertEqual(chat['title'], 'B', "pseudonyme, jamais le vrai nom")
        cid = chat['id']
        self.assertEqual(self.open_chat(self.b, self.a).json()['chat']['id'], cid, "même conversation dans les deux sens")

        sent = self.call('POST', f'/chats/{cid}/messages', self.a, {'body': "Salut <b>toi</b> !"})
        self.assertEqual(sent.status_code, 200, sent.text)
        self.assertEqual(sent.json()['message']['body'], "Salut <b>toi</b> !", "texte rendu tel quel, jamais en HTML")
        self.assertTrue(sent.json()['message']['is_mine'])

        self.assertEqual(self.call('GET', '/chats/unread', self.b).json()['unread'], 1)
        listed = self.call('GET', '/chats', self.b).json()['chats']
        self.assertEqual(listed[0]['unread'], 1)
        self.assertEqual(listed[0]['last_message']['author_name'], 'A')
        messages = self.call('GET', f'/chats/{cid}/messages', self.b).json()['messages']
        self.assertEqual([m['body'] for m in messages], ["Salut <b>toi</b> !"])
        self.assertFalse(messages[0]['is_mine'])
        self.call('POST', f'/chats/{cid}/read', self.b, {'last_message_id': messages[-1]['id']})
        self.assertEqual(self.call('GET', '/chats/unread', self.b).json()['unread'], 0)

        # Relève des nouveaux messages et pagination vers le passé.
        for i in range(3):
            self.call('POST', f'/chats/{cid}/messages', self.b, {'body': f"m{i}"})
        newer = self.call('GET', f"/chats/{cid}/messages?after={messages[-1]['id']}", self.a).json()['messages']
        self.assertEqual([m['body'] for m in newer], ['m0', 'm1', 'm2'])
        older = self.call('GET', f"/chats/{cid}/messages?before={newer[1]['id']}&limit=1", self.a).json()['messages']
        self.assertEqual([m['body'] for m in older], ['m0'])

    def test_contact_policy_and_outsiders(self):
        self.assertEqual(self.open_chat(self.a, self.c).status_code, 403, "aucun lien : pas de nouvelle conversation")
        cid = self.open_chat(self.a, self.b).json()['chat']['id']
        # C n'est pas membre de la conversation de A et B.
        self.assertEqual(self.call('GET', f'/chats/{cid}/messages', self.c).status_code, 404)
        self.assertEqual(self.call('POST', f'/chats/{cid}/messages', self.c, {'body': 'intrus'}).status_code, 404)
        self.assertEqual(self.call('GET', '/chats', self.c).json()['chats'], [])

    def test_block_stops_messages(self):
        cid = self.open_chat(self.a, self.b).json()['chat']['id']
        self.env['social_safety.block'].sudo().create({'blocker_id': self.b.id, 'blocked_id': self.a.id})
        self.assertEqual(self.call('POST', f'/chats/{cid}/messages', self.a, {'body': 'encore'}).status_code, 403)
        self.assertEqual(self.open_chat(self.a, self.b).status_code, 403)

    def test_relation_conversation(self):
        Relation = self.env['social_relation.relation']
        relation = Relation.with_user(self.a).action_create_relation("A, B et C")
        relation.with_user(self.a).action_invite(self.c)
        relation.with_user(self.c).action_accept()
        chats = self.call('GET', '/chats', self.c).json()['chats']
        self.assertEqual(len(chats), 1)
        self.assertEqual(chats[0]['kind'], 'relation')
        self.assertEqual(chats[0]['relation_id'], relation.id)
        self.assertEqual(chats[0]['title'], "A, B et C")
        cid = chats[0]['id']
        self.assertEqual(self.call('POST', f'/chats/{cid}/messages', self.c, {'body': 'Bonjour à vous'}).status_code, 200)
        self.assertEqual(self.call('GET', '/chats/unread', self.a).json()['unread'], 1)
        # Quitter la relation retire de sa conversation.
        relation.with_user(self.c).action_leave()
        self.assertEqual(self.call('GET', f'/chats/{cid}/messages', self.c).status_code, 404)

    def test_validation(self):
        cid = self.open_chat(self.a, self.b).json()['chat']['id']
        self.assertEqual(self.call('POST', f'/chats/{cid}/messages', self.a, {'body': '   '}).status_code, 403)
        self.assertEqual(self.call('POST', f'/chats/{cid}/messages', self.a, {'body': 'x' * 4001}).status_code, 403)
        self.assertEqual(self.call('POST', '/chats', self.a, {'user_id': self.a.id}).status_code, 403)
        outsider = new_test_user(self.env, login='hors.chat@example.com', groups='base.group_portal')
        self.assertEqual(self.call('GET', '/chats', outsider).status_code, 403)
