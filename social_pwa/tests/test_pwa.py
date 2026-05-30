import json
from unittest.mock import patch

from odoo.tests import HttpCase, TransactionCase, tagged


@tagged('social_pwa', 'pwa')
class TestPwaManifest(HttpCase):

    def test_manifest_served_with_correct_content_type(self):
        resp = self.url_open('/manifest.webmanifest')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('manifest+json', resp.headers.get('Content-Type', ''))

    def test_manifest_is_valid_json(self):
        resp = self.url_open('/manifest.webmanifest')
        data = json.loads(resp.text)
        # Required Web App Manifest fields
        self.assertIn('name', data)
        self.assertIn('short_name', data)
        self.assertIn('icons', data)
        self.assertIn('start_url', data)
        self.assertEqual(data['display'], 'standalone')

    def test_manifest_uses_camouflaged_defaults(self):
        """The default app name must match the existing social_safety camouflage."""
        resp = self.url_open('/manifest.webmanifest')
        data = json.loads(resp.text)
        self.assertEqual(data['name'], 'MétéoMédia')

    def test_manifest_picks_up_ir_config_parameter_overrides(self):
        ICP = self.env['ir.config_parameter'].sudo()
        ICP.set_param('social_pwa.app_name', 'CustomApp')
        ICP.set_param('social_pwa.theme_color', '#123456')
        resp = self.url_open('/manifest.webmanifest')
        data = json.loads(resp.text)
        self.assertEqual(data['name'], 'CustomApp')
        self.assertEqual(data['theme_color'], '#123456')


@tagged('social_pwa', 'pwa')
class TestPwaServiceWorker(HttpCase):

    def test_sw_served_at_root_with_correct_headers(self):
        resp = self.url_open('/sw.js')
        self.assertEqual(resp.status_code, 200)
        ct = resp.headers.get('Content-Type', '')
        self.assertIn('javascript', ct)
        # Service-Worker-Allowed must allow root scope.
        self.assertEqual(resp.headers.get('Service-Worker-Allowed'), '/')
        # Browsers re-fetch the SW script on every navigation — no caching.
        cache = resp.headers.get('Cache-Control', '')
        self.assertIn('no-cache', cache)

    def test_sw_body_includes_install_handler(self):
        resp = self.url_open('/sw.js')
        self.assertIn('addEventListener', resp.text)
        self.assertIn("'install'", resp.text)


@tagged('social_pwa', 'pwa')
class TestPwaSubscribe(HttpCase):

    def setUp(self):
        super().setUp()
        self.user = self.env['res.users'].create({
            'name': 'PWA User', 'login': 'pwa_user',
            'email': 'pwa_user@pwa.test',
            'password': 'Test1234!',
            'group_ids': [(4, self.env.ref('base.group_user').id)],
        })

    def test_subscribe_creates_subscription_for_current_user(self):
        self.authenticate('pwa_user', 'Test1234!')
        payload = {
            'jsonrpc': '2.0',
            'params': {
                'endpoint': 'https://push.example.com/abc',
                'keys': {'p256dh': 'p_xxx', 'auth': 'a_xxx'},
            },
        }
        resp = self.opener.post(
            self.base_url() + '/pwa/subscribe',
            json=payload,
            headers={'Content-Type': 'application/json'},
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body['result']['success'])

        sub = self.env['social_pwa.subscription'].sudo().search([
            ('endpoint', '=', 'https://push.example.com/abc'),
        ], limit=1)
        self.assertTrue(sub)
        self.assertEqual(sub.user_id, self.user)
        self.assertEqual(sub.p256dh, 'p_xxx')
        self.assertEqual(sub.auth, 'a_xxx')

    def test_subscribe_rejects_missing_keys(self):
        self.authenticate('pwa_user', 'Test1234!')
        payload = {'jsonrpc': '2.0', 'params': {'endpoint': 'https://push.example.com/x'}}
        resp = self.opener.post(
            self.base_url() + '/pwa/subscribe',
            json=payload,
            headers={'Content-Type': 'application/json'},
        )
        self.assertFalse(resp.json()['result']['success'])


@tagged('social_pwa', 'pwa', 'push_service')
class TestPushService(TransactionCase):

    def setUp(self):
        super().setUp()
        self.user = self.env['res.users'].create({
            'name': 'Push User', 'login': 'push_user',
            'email': 'push_user@push.test',
            'group_ids': [(4, self.env.ref('base.group_user').id)],
        })
        self.Service = self.env['social_pwa.push_service']

    def test_send_is_noop_when_vapid_not_configured(self):
        # No private key set → service must return 0 without raising.
        sent = self.Service.send_to_user(self.user.id)
        self.assertEqual(sent, 0)

    def test_payload_is_generic_constant(self):
        payload = self.Service._generic_payload()
        # The payload must not contain anything identifying the recipient
        # or the notification type.
        self.assertEqual(payload['title'], 'MétéoMédia')
        self.assertIn('Nouvelle activité', payload['body'])

    def test_send_skips_when_no_subscriptions(self):
        self.env['ir.config_parameter'].sudo().set_param(
            'social_pwa.vapid_private_key', 'dummy-key',
        )
        self.env['ir.config_parameter'].sudo().set_param(
            'social_pwa.vapid_sub', 'mailto:admin@test.test',
        )
        sent = self.Service.send_to_user(self.user.id)
        self.assertEqual(sent, 0)

    def test_send_invokes_webpusher_for_each_subscription(self):
        """With pywebpush available and VAPID configured, send_to_user
        calls WebPusher.send() once per subscription with the generic
        payload — and nothing else."""
        ICP = self.env['ir.config_parameter'].sudo()
        ICP.set_param('social_pwa.vapid_private_key', 'dummy-key')
        ICP.set_param('social_pwa.vapid_sub', 'mailto:admin@test.test')

        self.env['social_pwa.subscription'].create([
            {'user_id': self.user.id, 'endpoint': 'https://push.example.com/a',
             'p256dh': 'p1', 'auth': 'a1'},
            {'user_id': self.user.id, 'endpoint': 'https://push.example.com/b',
             'p256dh': 'p2', 'auth': 'a2'},
        ])

        calls = []

        class _StubPusher:
            def __init__(self, info):
                calls.append(('init', info))

            def send(self, data, vapid_private_key, vapid_claims, ttl):
                calls.append(('send', data))
                return type('R', (), {'status_code': 201})()

        with patch('odoo.addons.social_pwa.models.push_service.WebPusher', _StubPusher), \
             patch('odoo.addons.social_pwa.models.push_service.PYWEBPUSH_AVAILABLE', True):
            sent = self.Service.send_to_user(self.user.id)

        self.assertEqual(sent, 2)
        send_calls = [c for c in calls if c[0] == 'send']
        self.assertEqual(len(send_calls), 2)
        # Every push carries the exact same generic payload.
        for _, data in send_calls:
            parsed = json.loads(data)
            self.assertEqual(parsed['title'], 'MétéoMédia')

    def test_dead_subscription_removed_on_410(self):
        ICP = self.env['ir.config_parameter'].sudo()
        ICP.set_param('social_pwa.vapid_private_key', 'dummy-key')
        ICP.set_param('social_pwa.vapid_sub', 'mailto:admin@test.test')

        sub = self.env['social_pwa.subscription'].create({
            'user_id': self.user.id, 'endpoint': 'https://push.example.com/gone',
            'p256dh': 'p', 'auth': 'a',
        })

        from odoo.addons.social_pwa.models import push_service as ps

        class _GoneException(ps.WebPushException):
            def __init__(self):
                self.response = type('R', (), {'status_code': 410})()

        class _StubPusher:
            def __init__(self, info):
                pass

            def send(self, **kw):
                raise _GoneException()

        with patch.object(ps, 'WebPusher', _StubPusher), \
             patch.object(ps, 'PYWEBPUSH_AVAILABLE', True):
            self.Service.send_to_user(self.user.id)

        self.assertFalse(sub.exists(), 'sub deleted after HTTP 410')
