import contextlib
from unittest.mock import patch

from odoo import fields

from odoo.tests import tagged

from .test_call import MobileCallCase

TOKEN = {'a': 'a' * 64, 'b': 'b' * 64}
VOIP = {'a': 'a1' * 32, 'b': 'b1' * 32}


@tagged('post_install', '-at_install')
class TestCallRinging(MobileCallCase):
    """L'appel sonne sur l'iPhone (notification VoIP), puis la sonnerie s'arrête."""

    def setUp(self):
        super().setUp()
        Param = self.env['ir.config_parameter'].sudo()
        for key, value in (('social_mobile_push.team_id', 'TEAM'), ('social_mobile_push.key_id', 'KEY'),
                           ('social_mobile_push.apns_key', 'cle-de-test'), ('social_mobile_push.show_sender', 'False')):
            Param.search([('key', '=', key)]).unlink()
            Param.create({'key': key, 'value': value})
        Device = self.env['social_mobile.device']
        for name, user in (('a', self.a), ('b', self.b)):
            Device.with_user(user)._api_register(TOKEN[name], 'production')
            Device.with_user(user)._api_register(VOIP[name], 'production', 'voip')

        self.sent = []
        Queue = self.registry['social_mobile.push_queue']
        Channel = self.registry['discuss.channel']

        def fake_send(model, client, environment, token, topic, provider_jwt, payload, collapse_id, **options):
            self.sent.append({'token': token, 'topic': topic, 'payload': payload, 'options': options})
            return 200, None

        def send_now(channel, device_ids, payload, config):
            channel.env['social_mobile.push_queue']._mobile_call_send(device_ids, payload, config)

        self.startPatcher(patch.object(Queue, '_send', fake_send))
        self.startPatcher(patch.object(Queue, '_http_client', lambda model: contextlib.nullcontext()))
        self.startPatcher(patch.object(Channel, '_mobile_call_push_schedule', send_now))
        self.startPatcher(patch('odoo.addons.social_mobile_push.models.apns.provider_token', lambda *a, **k: 'jwt'))

    def pushes(self):
        sent, self.sent = self.sent, []
        return sent

    def test_ring_then_answered_on_the_phone(self):
        self.join(self.a)
        [ring] = self.pushes()
        self.assertEqual(ring['token'], VOIP['b'], "seul le jeton VoIP de l'appelé sonne")
        self.assertEqual(ring['topic'], 'com.diversecite.app.voip')
        self.assertEqual(ring['options']['push_type'], 'voip')
        self.assertTrue(ring['options']['expiration'])
        payload = ring['payload']
        self.assertEqual((payload['type'], payload['event'], payload['chat_id']), ('call', 'ring', self.chat_id))
        self.assertEqual(payload['caller'], "Diverse-Cité", "discret par défaut")

        self.join(self.b)
        self.assertEqual(self.pushes(), [], "l'iPhone qui répond sait déjà que ça ne sonne plus")

    def test_caller_hangs_up_before_answer(self):
        sid = self.join(self.a).json()['session_id']
        [ring] = self.pushes()
        self.call('POST', f'/chats/{self.chat_id}/call/leave', self.a, {'session_id': sid})
        [end] = self.pushes()
        self.assertEqual((end['token'], end['payload']['event']), (VOIP['b'], 'end'))
        self.assertEqual(end['payload']['call_id'], ring['payload']['call_id'], "même appel pour CallKit")

    def test_answered_on_the_web_stops_the_phone(self):
        self.join(self.a)
        [ring] = self.pushes()
        with patch(self.REQUESTS_GET, side_effect=self.fake_sfu):
            self.member(self.b).with_user(self.b).sudo()._rtc_join_call()
        [end] = self.pushes()
        self.assertEqual((end['token'], end['payload']['event']), (VOIP['b'], 'end'))
        self.assertEqual(end['payload']['call_id'], ring['payload']['call_id'])

    def test_decline_on_the_phone(self):
        self.join(self.a)
        self.pushes()
        self.call('POST', f'/chats/{self.chat_id}/call/decline', self.b, {})
        self.assertEqual(self.pushes(), [], "pas de notification vers l'iPhone qui a refusé")
        self.assertTrue(self.channel.rtc_session_ids, "l'appelant reste en ligne")

    def test_sender_name_and_mute(self):
        self.env['ir.config_parameter'].sudo().search([('key', '=', 'social_mobile_push.show_sender')]).value = 'True'
        self.join(self.a)
        [ring] = self.pushes()
        self.assertEqual(ring['payload']['caller'], 'A', "pseudonyme seulement")
        self.call('POST', f'/chats/{self.chat_id}/call/leave', self.a,
                  {'session_id': self.channel.rtc_session_ids.id})
        self.pushes()

        self.member(self.b).mute_until_dt = fields.Datetime.add(fields.Datetime.now(), days=1)
        self.join(self.a)
        self.assertEqual(self.pushes(), [], "conversation en sourdine : pas de sonnerie")

    def test_without_apns_key_nothing_rings(self):
        self.env['ir.config_parameter'].sudo().search([('key', '=', 'social_mobile_push.apns_key')]).unlink()
        self.join(self.a)
        self.assertEqual(self.pushes(), [])
