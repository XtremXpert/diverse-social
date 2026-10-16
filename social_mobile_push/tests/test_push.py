import contextlib
import json
from unittest.mock import patch

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from odoo.exceptions import AccessError, ValidationError
from odoo.tests import HttpCase, new_test_user, tagged

from odoo.addons.social_mobile_push.models import apns

API = '/api/social/v1'
TOKEN_A = 'a' * 64
TOKEN_B = 'b' * 64


@tagged('post_install', '-at_install')
class TestPush(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.admin = cls.env.ref('base.user_admin')
        cls.a, cls.b, cls.c = (cls._make_member(f'{n}.push@example.com') for n in 'abc')
        Connection = cls.env['club_social_profile.connection'].sudo()
        for x, y in ((cls.a, cls.b), (cls.b, cls.a)):
            Connection.create({'user_id': x.id, 'connected_user_id': y.id, 'state': 'accepted'})
        key = ec.generate_private_key(ec.SECP256R1())
        cls.pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                    serialization.NoEncryption()).decode()
        cls.public_key = key.public_key()
        ICP = cls.env['ir.config_parameter'].sudo()
        ICP.set_str('social_mobile_push.team_id', 'TEAM123456')
        ICP.set_str('social_mobile_push.key_id', 'KEY1234567')
        ICP.set_str('social_mobile_push.apns_key', cls.pem)
        Device = cls.env['social_mobile.device']
        Device.with_user(cls.a)._api_register(TOKEN_A, 'production')
        Device.with_user(cls.b)._api_register(TOKEN_B, 'sandbox')

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

    def setUp(self):
        super().setUp()
        self.sent = []
        self.responses = []
        Queue = self.registry['social_mobile.push_queue']

        def fake_send(model, client, environment, token, topic, provider_jwt, payload, collapse_id):
            self.sent.append({'environment': environment, 'token': token, 'topic': topic, 'jwt': provider_jwt,
                              'payload': payload, 'collapse': collapse_id})
            return self.responses.pop(0) if self.responses else (200, None)

        self.startPatcher(patch.object(Queue, '_send', fake_send))
        self.startPatcher(patch.object(Queue, '_http_client', lambda model: contextlib.nullcontext()))

    def dispatch(self):
        self.env['social_mobile.push_queue']._cron_dispatch()

    def chat(self):
        return self.env['discuss.channel']._mobile_open_chat(self.a, self.b)

    def test_message_notifies_the_other_member_discreetly(self):
        channel = self.chat()
        channel._mobile_post(self.a, "Message très privé")
        self.dispatch()
        self.assertEqual(len(self.sent), 1)
        push = self.sent[0]
        self.assertEqual(push['token'], TOKEN_B)
        self.assertEqual(push['environment'], 'sandbox')
        self.assertEqual(push['topic'], 'com.diversecite.app')
        alert = push['payload']['aps']['alert']
        self.assertEqual(alert['body'], "Nouveau message")
        self.assertNotIn("privé", json.dumps(push['payload']), "jamais le contenu du message")
        self.assertEqual(push['payload']['chat_id'], channel.id)
        self.assertEqual(push['payload']['aps']['badge'], 1)
        # Jeton de fournisseur ES256 signé par la clé .p8, avec l'équipe et la clé.
        claims = jwt.decode(push['jwt'], self.public_key, algorithms=['ES256'])
        self.assertEqual(claims['iss'], 'TEAM123456')
        self.assertEqual(jwt.get_unverified_header(push['jwt'])['kid'], 'KEY1234567')

    def test_burst_gives_one_notification(self):
        channel = self.chat()
        for i in range(3):
            channel._mobile_post(self.a, f"m{i}")
        self.dispatch()
        self.assertEqual(len(self.sent), 1)
        self.assertEqual(self.sent[0]['payload']['aps']['badge'], 3)

    def test_muted_and_revoked_members_get_nothing(self):
        channel = self.chat()
        member = channel.sudo().channel_member_ids.filtered(lambda m: m.partner_id == self.b.partner_id)
        member.mute_until_dt = '2099-01-01 00:00:00'
        channel._mobile_post(self.a, "chut")
        self.dispatch()
        self.assertEqual(self.sent, [])
        member.mute_until_dt = False
        channel._mobile_post(self.a, "encore")
        self.b.sudo().write({'group_ids': [(3, self.env.ref('social_base.group_social_user').id)]})
        self.dispatch()
        self.assertEqual(self.sent, [], "accès retiré (chaîne de confiance) : plus de notification")

    def test_relation_invitation_and_proposal(self):
        Relation = self.env['social_relation.relation']
        relation = Relation.with_user(self.a).action_create_relation("Couple")
        relation.with_user(self.a).action_invite(self.b)
        self.dispatch()
        self.assertEqual([(p['token'], p['payload']['aps']['alert']['body']) for p in self.sent],
                         [(TOKEN_B, "Vous êtes invité·e dans une relation")])
        self.assertEqual(self.sent[0]['payload']['relation_id'], relation.id)
        relation.with_user(self.b).action_accept()
        self.sent.clear()
        relation.with_user(self.b).action_invite(self.c)  # A doit approuver
        self.dispatch()
        self.assertEqual([(p['token'], p['payload']['aps']['alert']['body']) for p in self.sent],
                         [(TOKEN_A, "Une proposition attend votre accord")])

    def test_apple_responses(self):
        channel = self.chat()
        # Mauvais serveur (app installée par Xcode) : on réessaie sur l'autre et on corrige l'appareil.
        device_b = self.env['social_mobile.device'].sudo().search([('user_id', '=', self.b.id)])
        device_b.environment = 'production'
        self.responses = [(400, 'BadDeviceToken'), (200, None)]
        channel._mobile_post(self.a, "un")
        self.dispatch()
        self.assertEqual([p['environment'] for p in self.sent], ['production', 'sandbox'])
        self.assertEqual(device_b.environment, 'sandbox')
        # Application désinstallée : l'appareil est retiré.
        self.responses = [(410, 'Unregistered')]
        channel._mobile_post(self.a, "deux")
        self.dispatch()
        self.assertFalse(device_b.exists())

    def test_temporary_failure_is_retried(self):
        channel = self.chat()
        self.responses = [(503, None)]
        channel._mobile_post(self.a, "un")
        self.dispatch()
        row = self.env['social_mobile.push_queue'].sudo().search([('user_id', '=', self.b.id)])
        self.assertEqual((row.state, row.attempts), ('pending', 1))
        row.next_try = '2000-01-01 00:00:00'
        self.dispatch()
        self.assertEqual(row.state, 'done')
        self.assertEqual(len(self.sent), 2)

    def test_without_key_nothing_is_sent(self):
        self.env['ir.config_parameter'].sudo().set_str('social_mobile_push.apns_key', '')
        self.chat()._mobile_post(self.a, "un")
        self.dispatch()
        self.assertEqual(self.sent, [])
        self.assertFalse(self.env['social_mobile.push_queue'].sudo().search([('state', '=', 'pending')]))

    def test_token_follows_the_account(self):
        # Même iPhone, autre compte : le jeton change de propriétaire, jamais de doublon.
        self.env['social_mobile.device'].with_user(self.c)._api_register(TOKEN_B, 'sandbox')
        devices = self.env['social_mobile.device'].sudo().search([('token', '=', TOKEN_B)])
        self.assertEqual(devices.user_id, self.c)
        self.chat()._mobile_post(self.a, "pour B")
        self.dispatch()
        self.assertEqual(self.sent, [], "B n'a plus d'appareil")

    def call(self, method, path, user, body=None):
        key, _exp = self.env['res.users.apikeys'].with_user(user)._social_mobile_generate('test')
        headers = {'Content-Type': 'application/json', 'Authorization': f'Bearer {key}'}
        return self.url_open(API + path, data=json.dumps(body) if body is not None else None, headers=headers, method=method)

    def test_api(self):
        Device = self.env['social_mobile.device'].sudo()
        self.assertEqual(self.call('POST', '/devices', self.c, {'token': 'pas-un-jeton'}).status_code, 400)
        self.assertEqual(self.call('POST', '/devices', self.c, {'token': 'c' * 64, 'environment': 'sandbox'}).status_code, 200)
        self.assertEqual(Device.search([('user_id', '=', self.c.id)]).environment, 'sandbox')
        self.assertEqual(self.call('POST', '/devices', self.c, {'token': 'd' * 64, 'kind': 'voip'}).status_code, 200)
        self.assertEqual(self.call('POST', '/devices', self.c, {'token': 'e' * 64, 'kind': 'fax'}).status_code, 400)
        self.assertEqual(sorted(Device.search([('user_id', '=', self.c.id)]).mapped('kind')), ['alert', 'voip'],
                         "deux jetons pour un iPhone : notifications et appels")
        self.dispatch()
        self.assertFalse([s for s in self.sent if s['token'] == 'd' * 64], "jamais de notification sur le jeton VoIP")
        self.call('DELETE', '/devices', self.c, {'token': 'c' * 64})
        self.call('DELETE', '/devices', self.c, {'token': 'd' * 64})
        self.assertFalse(Device.search([('user_id', '=', self.c.id)]))
        # Suppression du compte : ses iPhone ne reçoivent plus rien.
        self.assertEqual(self.call('DELETE', '/me', self.a).status_code, 200)
        self.assertFalse(Device.search([('user_id', '=', self.a.id)]))

    def test_provider_token_is_cached(self):
        first = apns.provider_token('T', 'K', self.pem, now=1_000_000)
        self.assertEqual(apns.provider_token('T', 'K', self.pem, now=1_000_000 + 600), first)
        self.assertNotEqual(apns.provider_token('T', 'K', self.pem, now=1_000_000 + 46 * 60), first)

    def send_test(self, device, user, **vals):
        action = device.with_user(user).action_send_test()
        self.assertEqual(action['res_model'], 'social_mobile.test_push')
        Wizard = self.env['social_mobile.test_push'].with_user(user).with_context(action['context'])
        return Wizard.create(vals).action_send()

    def test_admin_test_notification(self):
        device = self.env['social_mobile.device'].sudo().search([('token', '=', TOKEN_B)])
        action = self.send_test(device, self.admin)
        self.assertEqual(action['params']['type'], 'success')
        self.assertEqual((self.sent[0]['token'], self.sent[0]['environment']), (TOKEN_B, 'sandbox'))
        self.assertEqual(self.sent[0]['payload']['aps']['alert'], {'title': "Diverse-Cité", 'body': "Notification d'essai"})
        # Texte modifiable.
        self.send_test(device, self.admin, title="Essai", body="Bonjour de l'équipe")
        self.assertEqual(self.sent[1]['payload']['aps']['alert'], {'title': "Essai", 'body': "Bonjour de l'équipe"})
        with self.assertRaises(ValidationError):
            self.send_test(device, self.admin, body="x" * 500)
        # Jeton périmé : l'appareil est retiré, et l'admin le sait.
        self.responses = [(410, 'Unregistered')]
        self.assertEqual(self.send_test(device, self.admin)['params']['type'], 'warning')
        self.assertFalse(device.exists())
        # Réservé aux administrateurs système.
        device = self.env['social_mobile.device'].sudo().search([('token', '=', TOKEN_A)])
        with self.assertRaises(AccessError):
            device.with_user(self.a).action_send_test()
        with self.assertRaises(AccessError):
            device.with_user(self.a)._send_test("Essai", "Essai")
