import json
from unittest.mock import patch

import requests

from odoo.tests import HttpCase, new_test_user, tagged

from odoo.addons.mail.tools import discuss, jwt
from odoo.addons.mail.tools.discuss import Store

API = '/api/social/v1'
SFU_URL = 'https://sfu.example.com'
REQUESTS_GET = 'odoo.addons.mail.models.discuss.discuss_channel_member.requests.get'


class FakeSfuResponse:
    """Réponse de /v1/channel du SFU : un nouveau canal à chaque appel."""
    count = 0

    def __init__(self):
        FakeSfuResponse.count += 1
        self.uuid = f'sfu-channel-{FakeSfuResponse.count}'

    def raise_for_status(self):
        pass

    def json(self):
        return {'uuid': self.uuid, 'url': SFU_URL}


def fake_sfu(*_args, **_kwargs):
    return FakeSfuResponse()


class MobileCallCase(HttpCase):
    """Deux membres reliés (A, B) et un troisième (C), une conversation entre A et B, un SFU simulé."""
    REQUESTS_GET = REQUESTS_GET
    fake_sfu = staticmethod(fake_sfu)

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.admin = cls.env.ref('base.user_admin')
        cls.a, cls.b, cls.c = (cls._make_member(f'{n}.call@example.com') for n in 'abc')
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

    def setUp(self):
        super().setUp()
        self._configure_sfu()
        self.chat_id = self.call('POST', '/chats', self.a, {'user_id': self.b.id}).json()['chat']['id']
        self.channel = self.env['discuss.channel'].sudo().browse(self.chat_id)

    def _configure_sfu(self, enabled=True):
        Param = self.env['ir.config_parameter'].sudo()
        for key, value in (
            ('mail.use_call_server', 'True' if enabled else 'False'),
            ('mail.use_sfu_server', 'True' if enabled else 'False'),
            ('mail.sfu_server_url', SFU_URL),
            ('mail.sfu_server_key', 'dGVzdC1zZnUta2V5LXRlc3Qtc2Z1LWtleS10ZXN0LXNmdQ=='),
        ):
            Param.search([('key', '=', key)]).unlink()
            Param.create({'key': key, 'value': value})

    def call(self, method, path, user, body=None):
        key, _exp = self.env['res.users.apikeys'].with_user(user)._social_mobile_generate('test')
        headers = {'Content-Type': 'application/json', 'Authorization': f'Bearer {key}'}
        return self.url_open(API + path, data=json.dumps(body) if body is not None else None, headers=headers, method=method)

    def join(self, user):
        with patch(REQUESTS_GET, side_effect=fake_sfu):
            return self.call('POST', f'/chats/{self.chat_id}/call/join', user, {})

    def member(self, user):
        return self.channel.channel_member_ids.filtered(lambda m: m.partner_id == user.partner_id)


@tagged('post_install', '-at_install')
class TestMobileCall(MobileCallCase):

    def test_join_through_sfu(self):
        res = self.join(self.a)
        self.assertEqual(res.status_code, 200, res.text)
        data = res.json()
        self.assertEqual(data['server']['url'], SFU_URL)
        self.assertTrue(data['server']['channel_uuid'], "l'application passe par le SFU dès le premier participant")
        claims = jwt.verify(data['server']['token'], discuss.get_derived_sfu_key(self.env, self.chat_id),
                            algorithm=jwt.Algorithm.HS256)
        self.assertEqual(claims['session_id'], data['session_id'])
        self.assertEqual(claims['sfu_channel_uuid'], data['server']['channel_uuid'])
        self.assertEqual(claims['user_id'], self.a.id, "le jeton identifie le membre qui a rejoint")
        self.assertEqual([p['name'] for p in data['call']['participants']], ['A'], "pseudonyme seulement")
        self.assertTrue(data['call']['participants'][0]['is_self'])

        chat_b = self.call('GET', f'/chats/{self.chat_id}', self.b).json()['chat']
        self.assertEqual(chat_b['call'], {'active': True, 'participant_count': 1, 'ringing': True},
                         "l'appel sonne chez l'autre membre")

        res_b = self.join(self.b)
        self.assertEqual(res_b.status_code, 200, res_b.text)
        self.assertEqual(res_b.json()['server']['channel_uuid'], data['server']['channel_uuid'],
                         "même canal SFU pour les deux participants")
        self.assertFalse(res_b.json()['call']['ringing'], "rejoindre arrête la sonnerie")
        self.assertEqual(res_b.json()['call']['participant_count'], 2)

    def test_web_participant_stays_on_sfu(self):
        """Sous trois participants, Odoo repasserait l'appel en pair-à-pair à l'arrivée du site."""
        data = self.join(self.a).json()
        store = Store()
        with patch(REQUESTS_GET, side_effect=fake_sfu):
            self.member(self.b).with_user(self.b).sudo()._rtc_join_call(store)
        self.assertEqual(self.channel.sfu_channel_uuid, data['server']['channel_uuid'])
        rtc = store.as_dict()['Rtc']
        rtc = rtc[0] if isinstance(rtc, list) else rtc
        self.assertTrue(rtc['serverInfo'], "le site reçoit le SFU, pas du pair-à-pair")
        self.assertEqual(rtc['serverInfo']['channelUUID'], data['server']['channel_uuid'])

    def test_ping_mute_leave(self):
        sid = self.join(self.a).json()['session_id']
        ping = self.call('POST', f'/chats/{self.chat_id}/call/ping', self.a, {'session_id': sid})
        self.assertEqual(ping.status_code, 200, ping.text)
        muted = self.call('POST', f'/chats/{self.chat_id}/call/mute', self.a, {'session_id': sid, 'muted': True})
        self.assertTrue(muted.json()['call']['participants'][0]['is_muted'])
        self.assertEqual(self.call('POST', f'/chats/{self.chat_id}/call/ping', self.b, {'session_id': sid}).status_code,
                         410, "la session d'un autre membre ne se maintient pas")

        left = self.call('POST', f'/chats/{self.chat_id}/call/leave', self.a, {'session_id': sid})
        self.assertEqual(left.status_code, 200, left.text)
        self.assertFalse(left.json()['call']['active'])
        self.assertFalse(self.channel.sfu_channel_uuid, "le canal SFU est libéré à la fin de l'appel")
        self.assertEqual(self.call('POST', f'/chats/{self.chat_id}/call/ping', self.a, {'session_id': sid}).status_code,
                         410, "l'application apprend que l'appel est fini")

    def test_decline(self):
        self.join(self.a)
        res = self.call('POST', f'/chats/{self.chat_id}/call/decline', self.b, {})
        self.assertEqual(res.status_code, 200, res.text)
        self.assertFalse(res.json()['call']['ringing'])
        self.assertTrue(res.json()['call']['active'], "refuser ne coupe pas l'appel de l'autre")

    def test_refusals(self):
        self.assertEqual(self.join(self.c).status_code, 404, "hors de la conversation : introuvable")

        self.env['social_safety.block'].sudo().create({'blocker_id': self.b.id, 'blocked_id': self.a.id})
        res = self.join(self.a)
        self.assertEqual(res.status_code, 403, res.text)
        self.assertFalse(self.channel.rtc_session_ids)

    def test_sfu_unavailable(self):
        self._configure_sfu(enabled=False)
        self.assertEqual(self.join(self.a).status_code, 503)

        self._configure_sfu()
        with patch(REQUESTS_GET, side_effect=requests.exceptions.ConnectionError()):
            res = self.call('POST', f'/chats/{self.chat_id}/call/join', self.a, {})
        self.assertEqual(res.status_code, 503, res.text)
        self.assertFalse(self.channel.rtc_session_ids, "pas d'appel qui sonne sans serveur pour le tenir")
