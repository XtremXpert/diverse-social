import contextlib
import json
from unittest.mock import patch

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa

from odoo import Command
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import HttpCase, new_test_user, tagged
from odoo.tools import BinaryBytes

from odoo.addons.social_mobile_push.models import apns, fcm

API = '/api/social/v1'
TOKEN_A = 'a' * 64
TOKEN_B = 'b' * 64
# Jeton FCM : casse mêlée, deux-points ; il ne doit jamais être mis en minuscules.
FCM_B = 'dQw4w9WgXcQ:APA91bH' + 'Ab_-' * 40


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
        rsa_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cls.rsa_public_key = rsa_key.public_key()
        cls.service_account = {
            'type': 'service_account', 'project_id': 'diverse-cite-test', 'private_key_id': 'kid123',
            'private_key': rsa_key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                                 serialization.NoEncryption()).decode(),
            'client_email': 'fcm@diverse-cite-test.iam.gserviceaccount.com',
            'token_uri': 'https://oauth2.googleapis.com/token',
        }
        ICP.set_str('social_mobile_push.fcm_service_account', json.dumps(cls.service_account))

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

        self.fcm_sent = []
        self.fcm_responses = []
        self.access_tokens = 0

        def fake_send_fcm(model, client, project_id, token, message):
            self.fcm_sent.append({'project': project_id, 'access': token, 'message': message})
            return self.fcm_responses.pop(0) if self.fcm_responses else (200, None)

        def fake_access_token(model, client, config):
            self.access_tokens += 1
            return 'acces-%s' % self.access_tokens

        self.startPatcher(patch.object(Queue, '_send', fake_send))
        self.startPatcher(patch.object(Queue, '_send_fcm', fake_send_fcm))
        self.startPatcher(patch.object(Queue, '_fcm_access_token', fake_access_token))
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

    def test_group_notifies_but_channel_does_not(self):
        Channel = self.env['discuss.channel'].sudo()
        members = [Command.create({'partner_id': u.partner_id.id}) for u in self.a | self.b]
        group = Channel.create({'name': '', 'channel_type': 'group', 'channel_member_ids': members})
        group._mobile_post(self.a, "au groupe")
        self.dispatch()
        self.assertEqual([p['token'] for p in self.sent], [TOKEN_B])
        self.sent.clear()
        channel = Channel.create({'name': 'Bénévoles', 'channel_type': 'channel', 'channel_member_ids': members})
        channel._mobile_post(self.a, "au canal")
        self.dispatch()
        self.assertEqual(self.sent, [], "canal Discuss : lu dans l'application, sans notification")

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

    # ── Android (FCM) ───────────────────────────────────────────────────────

    def register_android(self, user, token=FCM_B):
        return self.env['social_mobile.device'].with_user(user)._api_register(token, 'production', 'alert', 'fcm')

    def test_android_message_is_a_discreet_data_message(self):
        device = self.register_android(self.b)
        self.assertEqual((device.token, device.platform), (FCM_B, 'fcm'), "jeton gardé tel quel")
        channel = self.chat()
        channel._mobile_post(self.a, "Message très privé")
        self.dispatch()
        self.assertEqual([p['token'] for p in self.sent], [TOKEN_B], "l'iPhone de B reçoit toujours le sien")
        [push] = self.fcm_sent
        self.assertEqual(push['project'], 'diverse-cite-test')
        message = push['message']
        self.assertEqual(message['token'], FCM_B)
        self.assertNotIn('notification', message, "données seulement : l'application affiche la notification")
        self.assertEqual(message['android']['priority'], 'HIGH')
        self.assertEqual(message['android']['collapse_key'], 'chat-%s' % channel.id)
        data = message['data']
        self.assertEqual((data['type'], data['kind'], data['body']), ('alert', 'message', "Nouveau message"))
        self.assertEqual((data['chat_id'], data['badge']), (str(channel.id), '1'))
        self.assertTrue(all(isinstance(v, str) for v in data.values()), "FCM n'accepte que du texte")
        self.assertNotIn("privé", json.dumps(message), "jamais le contenu du message")

    def test_android_token_rules(self):
        Device = self.env['social_mobile.device']
        with self.assertRaises(ValidationError):
            Device.with_user(self.c)._api_register('court', 'production', 'alert', 'fcm')
        with self.assertRaises(ValidationError):
            Device.with_user(self.c)._api_register(FCM_B, 'production', 'voip', 'fcm')
        with self.assertRaises(ValidationError):
            Device.with_user(self.c)._api_register(FCM_B, 'production', 'alert', 'windows')
        self.assertEqual(self.call('POST', '/devices', self.c, {'token': FCM_B, 'platform': 'fcm'}).status_code, 200)
        device = Device.sudo().search([('user_id', '=', self.c.id)])
        self.assertEqual((device.token, device.platform, device.environment), (FCM_B, 'fcm', 'production'))
        self.call('DELETE', '/devices', self.c, {'token': FCM_B})
        self.assertFalse(device.exists(), "retiré avec son jeton exact")

    def test_google_responses(self):
        device = self.register_android(self.b)
        channel = self.chat()
        # Jeton d'accès refusé : on en demande un autre et on réessaie.
        self.fcm_responses = [(401, 'UNAUTHENTICATED'), (200, None)]
        channel._mobile_post(self.a, "un")
        self.dispatch()
        self.assertEqual([p['access'] for p in self.fcm_sent], ['acces-1', 'acces-2'])
        # Panne passagère : nouvel essai plus tard.
        self.fcm_sent.clear()
        self.fcm_responses = [(503, None)]
        channel._mobile_post(self.a, "deux")
        self.dispatch()
        row = self.env['social_mobile.push_queue'].sudo().search([('user_id', '=', self.b.id), ('state', '=', 'pending')])
        self.assertEqual(row.attempts, 1)
        row.unlink()
        # Application désinstallée : l'appareil est retiré.
        self.fcm_responses = [(404, 'UNREGISTERED')]
        channel._mobile_post(self.a, "trois")
        self.dispatch()
        self.assertFalse(device.exists())

    def test_without_firebase_android_gets_nothing(self):
        self.register_android(self.b)
        self.env['ir.config_parameter'].sudo().set_str('social_mobile_push.fcm_service_account', '')
        self.chat()._mobile_post(self.a, "un")
        self.dispatch()
        self.assertEqual(self.fcm_sent, [])
        self.assertEqual([p['token'] for p in self.sent], [TOKEN_B])
        # Firebase seul (pas de clé Apple) : Android reçoit, l'iPhone non.
        ICP = self.env['ir.config_parameter'].sudo()
        ICP.set_str('social_mobile_push.fcm_service_account', json.dumps(self.service_account))
        ICP.set_str('social_mobile_push.apns_key', '')
        self.sent.clear()
        self.chat()._mobile_post(self.a, "deux")
        self.dispatch()
        self.assertEqual(self.sent, [])
        self.assertEqual(len(self.fcm_sent), 1)

    def test_service_account_assertion_and_token_cache(self):
        account = fcm.parse_service_account(json.dumps(self.service_account))
        claims = jwt.decode(fcm.assertion(account), self.rsa_public_key, algorithms=['RS256'],
                            audience='https://oauth2.googleapis.com/token')
        self.assertEqual(claims['iss'], 'fcm@diverse-cite-test.iam.gserviceaccount.com')
        self.assertEqual(claims['scope'], 'https://www.googleapis.com/auth/firebase.messaging')
        self.assertEqual(claims['exp'] - claims['iat'], 3600)
        self.assertIsNone(fcm.parse_service_account('{"project_id": "x"}'), "compte incomplet")
        self.assertIsNone(fcm.parse_service_account('pas du json'))

        class Response:
            status_code = 200

            def raise_for_status(self):
                pass

            def json(self):
                return {'access_token': 'ya29.jeton', 'expires_in': 3600}

        class Client:
            calls = 0

            def post(self, url, data=None, **kwargs):
                Client.calls += 1
                return Response()

        fcm.forget_token(account)
        client = Client()
        self.assertEqual(fcm.access_token(client, account, now=1_000_000), 'ya29.jeton')
        self.assertEqual(fcm.access_token(client, account, now=1_000_000 + 600), 'ya29.jeton')
        self.assertEqual(Client.calls, 1, "jeton réutilisé")
        fcm.access_token(client, account, now=1_000_000 + 3400)
        self.assertEqual(Client.calls, 2, "renouvelé cinq minutes avant l'échéance")
        fcm.forget_token(account)

    def test_admin_test_notification_on_android(self):
        device = self.register_android(self.b)
        action = self.send_test(device, self.admin)
        self.assertEqual(action['params']['type'], 'success')
        self.assertEqual(self.fcm_sent[0]['message']['data'], {'type': 'alert', 'title': "Diverse-Cité", 'body': "Notification d'essai"})

    def test_service_account_file_upload(self):
        """Le fichier JSON téléversé remplit le champ du compte de service, puis il est oublié."""
        ICP = self.env['ir.config_parameter'].sudo()
        ICP.set_str('social_mobile_push.fcm_service_account', '')
        text = json.dumps(self.service_account)
        settings = self.env['res.config.settings'].new({
            'social_mobile_push_fcm_file': BinaryBytes(text.encode(), filename='diverse-cite-firebase.json'),
        })
        self.assertIsNone(settings._onchange_social_mobile_push_fcm_file())
        self.assertEqual(settings.social_mobile_push_fcm_service_account, text)
        self.assertFalse(settings.social_mobile_push_fcm_file)

        # Un autre fichier (la clé Apple, un google-services.json…) est refusé, le réglage reste.
        settings = self.env['res.config.settings'].new({
            'social_mobile_push_fcm_service_account': text,
            'social_mobile_push_fcm_file': BinaryBytes(b'{"project_info": {}}'),
        })
        self.assertIn('warning', settings._onchange_social_mobile_push_fcm_file())
        self.assertEqual(settings.social_mobile_push_fcm_service_account, text)
        self.assertFalse(settings.social_mobile_push_fcm_file)
