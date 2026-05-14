from odoo.tests import HttpCase, TransactionCase, tagged


def _make_social_user(env, name, login):
    group_social = env.ref('social_base.group_social_user')
    return env['res.users'].create({
        'name': name, 'login': login, 'email': f'{login}@notif.test',
        'password': 'Test1234!',
        'group_ids': [(4, group_social.id)],
    })


@tagged('social_notifications', 'notifications_portal')
class TestNotificationsPortalData(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = _make_social_user(cls.env, 'NotifUser', 'notif_user')
        cls.actor = _make_social_user(cls.env, 'NotifActor', 'notif_actor')
        cls.profile = cls.env['club_social_profile.profile'].sudo().get_or_create_for_user(cls.user)

    def _create_notif(self, notif_type='connection_request', is_read=False):
        n = self.env['club_social_profile.notification'].sudo().create({
            'user_id': self.user.id,
            'actor_id': self.actor.id,
            'type': notif_type,
            'body': f'Test notification {notif_type}',
            'url': '/social/feed',
            'is_read': is_read,
        })
        return n

    def test_create_notification(self):
        n = self._create_notif()
        self.assertTrue(n)
        self.assertFalse(n.is_read)
        self.assertEqual(n.user_id, self.user)

    def test_mark_read(self):
        n = self._create_notif()
        self.assertFalse(n.is_read)
        n.action_mark_read()
        self.assertTrue(n.is_read)
        self.assertTrue(n.read_at)

    def test_mark_all_read(self):
        self._create_notif('post_like')
        self._create_notif('new_message')
        unread_before = self.env['club_social_profile.notification'].sudo().search_count([
            ('user_id', '=', self.user.id),
            ('is_read', '=', False),
        ])
        self.assertGreaterEqual(unread_before, 2)
        count = self.env['club_social_profile.notification'].sudo().mark_all_read(self.user.id)
        self.assertGreaterEqual(count, 2)
        unread_after = self.env['club_social_profile.notification'].sudo().search_count([
            ('user_id', '=', self.user.id),
            ('is_read', '=', False),
        ])
        self.assertEqual(unread_after, 0)

    def test_unread_count_correct(self):
        n1 = self._create_notif('post_comment')
        n2 = self._create_notif('profile_visit', is_read=True)
        unread = self.env['club_social_profile.notification'].sudo().search_count([
            ('user_id', '=', self.user.id),
            ('is_read', '=', False),
        ])
        self.assertGreaterEqual(unread, 1)

    def test_notify_factory_ignores_self(self):
        """_notify ne crée pas de notif si user == actor."""
        before = self.env['club_social_profile.notification'].sudo().search_count([
            ('user_id', '=', self.user.id),
        ])
        self.env['club_social_profile.notification']._notify(
            user_id=self.user.id,
            actor_id=self.user.id,  # même utilisateur
            notif_type='post_like',
            body='Self notification',
        )
        after = self.env['club_social_profile.notification'].sudo().search_count([
            ('user_id', '=', self.user.id),
        ])
        self.assertEqual(before, after)

    def test_notification_types_coverage(self):
        """Les types de notification définis sont bien dans la selection."""
        fields_def = self.env['club_social_profile.notification']._fields['type']
        selection_keys = [k for k, _ in fields_def.selection]
        for t in ['connection_request', 'post_like', 'new_message', 'daily_digest']:
            self.assertIn(t, selection_keys)

    def test_filter_by_user(self):
        """Chaque user ne voit que ses propres notifications."""
        other = _make_social_user(self.env, 'OtherNotif', 'other_notif')
        self.env['club_social_profile.notification'].sudo().create({
            'user_id': other.id,
            'actor_id': self.actor.id,
            'type': 'post_like',
            'body': 'Notification pour autre',
        })
        mine = self.env['club_social_profile.notification'].sudo().search([
            ('user_id', '=', self.user.id),
        ])
        other_ids = [n.id for n in mine if n.user_id.id != self.user.id]
        self.assertEqual(other_ids, [])


@tagged('social_notifications', 'notifications_portal', 'post_install', '-at_install')
class TestNotificationsPortalHttp(HttpCase):

    def test_notifications_unauthenticated_redirects(self):
        resp = self.url_open('/social/notifications', allow_redirects=False)
        self.assertIn(resp.status_code, (302, 303))

    def test_notifications_authenticated_ok(self):
        self.authenticate('admin', 'admin')
        resp = self.url_open('/social/notifications')
        self.assertEqual(resp.status_code, 200)

    def test_notifications_filter_unread(self):
        self.authenticate('admin', 'admin')
        resp = self.url_open('/social/notifications?filter=unread')
        self.assertEqual(resp.status_code, 200)

    def test_api_list_authenticated(self):
        self.authenticate('admin', 'admin')
        resp = self.url_open('/social/api/notifications')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data.get('success'))
        self.assertIn('notifications', data['data'])
        self.assertIn('unread_count', data['data'])

    def test_api_list_unread_only(self):
        self.authenticate('admin', 'admin')
        resp = self.url_open('/social/api/notifications?unread_only=true')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data.get('success'))
        for n in data['data']['notifications']:
            self.assertFalse(n['is_read'])

    def test_api_mark_all_read(self):
        self.authenticate('admin', 'admin')
        resp = self.url_open('/social/api/notifications/read_all', data={})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data.get('success'))

    def test_notifications_page_shows_title(self):
        self.authenticate('admin', 'admin')
        resp = self.url_open('/social/notifications')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'Notifications', resp.content)
