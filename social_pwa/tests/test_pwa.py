import json

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
        ICP.set_str('social_pwa.app_name', 'CustomApp')
        ICP.set_str('social_pwa.theme_color', '#123456')
        resp = self.url_open('/manifest.webmanifest')
        data = json.loads(resp.text)
        self.assertEqual(data['name'], 'CustomApp')
        self.assertEqual(data['theme_color'], '#123456')

    def test_manifest_icons_default_to_camouflage(self):
        data = json.loads(self.url_open('/manifest.webmanifest').text)
        srcs = [icon['src'] for icon in data['icons']]
        self.assertIn('/social_pwa/static/src/img/icon-192.png', srcs)
        self.assertFalse(any('/marque/' in src for src in srcs))

    def test_manifest_icons_switch_to_brand(self):
        self.env['ir.config_parameter'].sudo().set_str('social_pwa.icon_set', 'marque')
        data = json.loads(self.url_open('/manifest.webmanifest').text)
        for icon in data['icons']:
            self.assertTrue(icon['src'].startswith('/social_pwa/static/src/img/marque/'))
            self.assertEqual(self.url_open(icon['src']).status_code, 200)

    def test_unknown_icon_set_falls_back_to_camouflage(self):
        self.env['ir.config_parameter'].sudo().set_str('social_pwa.icon_set', 'inconnu')
        data = json.loads(self.url_open('/manifest.webmanifest').text)
        self.assertFalse(any('/marque/' in icon['src'] for icon in data['icons']))

    def test_apple_touch_icon_follows_icon_set(self):
        self.env['ir.config_parameter'].sudo().set_str('social_pwa.icon_set', 'marque')
        html = self.url_open('/web/login').text
        self.assertIn('/social_pwa/static/src/img/marque/apple-touch-icon.png', html)


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

    def test_subscribe_creates_device_for_current_user(self):
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

        device = self.env['mail.push.device'].sudo().search([
            ('endpoint', '=', 'https://push.example.com/abc'),
        ], limit=1)
        self.assertTrue(device)
        self.assertEqual(device.partner_id, self.user.partner_id)
        self.assertEqual(json.loads(device.keys),
                         {'p256dh': 'p_xxx', 'auth': 'a_xxx'})

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

    def _device(self, user, endpoint):
        return self.env['mail.push.device'].sudo().create({
            'partner_id': user.partner_id.id,
            'endpoint': endpoint,
            'keys': json.dumps({'p256dh': 'p', 'auth': 'a'}),
        })

    def test_payload_is_generic_constant(self):
        payload = self.Service._generic_payload()
        # The payload must not contain anything identifying the recipient
        # or the notification type.
        self.assertEqual(payload['title'], 'MétéoMédia')
        self.assertIn('Nouvelle activité', payload['body'])

    def test_enqueue_skips_when_no_devices(self):
        sent = self.Service.enqueue_for_users([self.user.id])
        self.assertEqual(sent, 0)
        self.assertFalse(self.env['mail.push'].sudo().search([]))

    def test_enqueue_queues_one_push_per_device(self):
        self._device(self.user, 'https://push.example.com/a')
        self._device(self.user, 'https://push.example.com/b')

        sent = self.Service.enqueue_for_users([self.user.id])

        self.assertEqual(sent, 2)
        pushes = self.env['mail.push'].sudo().search([])
        self.assertEqual(len(pushes), 2)
        # Every push carries the exact same generic payload — no actor,
        # no notification type, no message preview.
        for push in pushes:
            parsed = json.loads(push.payload)
            self.assertEqual(parsed['title'], 'MétéoMédia')
            self.assertIn('Nouvelle activité', parsed['body'])

    def test_notification_create_enqueues_push(self):
        self._device(self.user, 'https://push.example.com/hook')
        actor = self.env['res.users'].create({
            'name': 'Actor', 'login': 'push_actor',
            'email': 'push_actor@push.test',
        })

        self.env['club_social_profile.notification']._notify(
            self.user.id, actor.id, 'connection_request', 'Hello',
        )

        pushes = self.env['mail.push'].sudo().search([])
        self.assertEqual(len(pushes), 1)
        parsed = json.loads(pushes.payload)
        self.assertEqual(parsed['title'], 'MétéoMédia')
        self.assertNotIn('Hello', pushes.payload)
        self.assertNotIn('Actor', pushes.payload)
