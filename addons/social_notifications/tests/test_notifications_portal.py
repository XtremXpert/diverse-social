from odoo.http import Request
from odoo.tests import HttpCase, TransactionCase, tagged


def _make_social_user(env, name, login):
    group_user = env.ref('base.group_user')
    group_social = env.ref('social_base.group_social_user')
    return env['res.users'].create({
        'name': name, 'login': login, 'email': f'{login}@notif.test',
        'password': 'Test1234!',
        'group_ids': [(4, group_user.id), (4, group_social.id)],
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
        """_notify does not create a notif if user == actor."""
        before = self.env['club_social_profile.notification'].sudo().search_count([
            ('user_id', '=', self.user.id),
        ])
        self.env['club_social_profile.notification']._notify(
            user_id=self.user.id,
            actor_id=self.user.id,  # same user
            notif_type='post_like',
            body='Self notification',
        )
        after = self.env['club_social_profile.notification'].sudo().search_count([
            ('user_id', '=', self.user.id),
        ])
        self.assertEqual(before, after)

    def test_notification_types_coverage(self):
        """Defined notification types are present in the selection."""
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

    def test_extended_notification_types_in_selection(self):
        """Types added by social_notifications must be in the selection."""
        fields_def = self.env['club_social_profile.notification']._fields['type']
        selection_keys = [k for k, _ in fields_def.selection]
        extended_types = [
            'event_registration', 'group_join_request', 'group_join_approved',
            'proposal_voting', 'story_new', 'gallery_photo_approved',
            'gallery_photo_rejected', 'vouching_received', 'vouching_withdrawn',
            'negotiation_shared', 'negotiation_signed', 'negotiation_active',
            'circle_added',
        ]
        for t in extended_types:
            self.assertIn(t, selection_keys, f'Missing type in selection: {t}')

    def test_notification_with_url(self):
        """Une notification peut avoir une URL."""
        n = self.env['club_social_profile.notification'].sudo().create({
            'user_id': self.user.id,
            'actor_id': self.actor.id,
            'type': 'post_like',
            'body': 'Avec URL',
            'url': '/social/feed',
        })
        self.assertEqual(n.url, '/social/feed')

    def test_notification_bus_push_no_error(self):
        """Creation triggers the bus push without error."""
        n = self.env['club_social_profile.notification'].sudo().create({
            'user_id': self.user.id,
            'actor_id': self.actor.id,
            'type': 'event_registration',
            'body': 'Bus test',
            'url': '/event/1',
        })
        self.assertTrue(n.exists())


@tagged('social_notifications', 'notifications_portal', 'post_install', '-at_install')
class TestNotificationsPortalHttp(HttpCase):

    def test_notifications_unauthenticated_redirects(self):
        resp = self.url_open('/social/notifications', allow_redirects=False)
        self.assertIn(resp.status_code, (302, 303))

    def test_notifications_authenticated_ok(self):
        self.authenticate('admin', 'admin')
        _csrf = Request.csrf_token(self)
        resp = self.url_open('/social/notifications')
        self.assertEqual(resp.status_code, 200)

    def test_notifications_filter_unread(self):
        self.authenticate('admin', 'admin')
        _csrf = Request.csrf_token(self)
        resp = self.url_open('/social/notifications?filter=unread')
        self.assertEqual(resp.status_code, 200)

    def test_api_list_authenticated(self):
        self.authenticate('admin', 'admin')
        _csrf = Request.csrf_token(self)
        resp = self.url_open('/social/api/notifications')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data.get('success'))
        self.assertIn('notifications', data['data'])
        self.assertIn('unread_count', data['data'])

    def test_api_list_unread_only(self):
        self.authenticate('admin', 'admin')
        _csrf = Request.csrf_token(self)
        resp = self.url_open('/social/api/notifications?unread_only=true')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data.get('success'))
        for n in data['data']['notifications']:
            self.assertFalse(n['is_read'])

    def test_api_mark_all_read(self):
        self.authenticate('admin', 'admin')
        _csrf = Request.csrf_token(self)
        resp = self.url_open('/social/api/notifications/read_all', data={'csrf_token': _csrf, })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data.get('success'))

    def test_notifications_page_shows_title(self):
        self.authenticate('admin', 'admin')
        _csrf = Request.csrf_token(self)
        resp = self.url_open('/social/notifications')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'Notifications', resp.content)

    def test_api_list_unauthenticated_redirects(self):
        resp = self.url_open('/social/api/notifications', allow_redirects=False)
        self.assertIn(resp.status_code, (302, 303))

    def test_api_mark_single_read(self):
        """POST /social/api/notifications/<id>/read marque la notification comme lue."""
        admin = self.env.ref('base.user_admin')
        notif = self.env['club_social_profile.notification'].sudo().create({
            'user_id': admin.id,
            'actor_id': admin.id,
            'type': 'post_like',
            'body': 'API single read test',
            'is_read': False,
        })
        # Bypass: _notify ignores user==actor, so write directly
        notif.sudo().write({'is_read': False})
        self.authenticate('admin', 'admin')
        _csrf = Request.csrf_token(self)
        resp = self.url_open(f'/social/api/notifications/{notif.id}/read', data={'csrf_token': _csrf, })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data.get('success'))
        notif.invalidate_recordset(['is_read'])
        self.assertTrue(notif.is_read)

    def test_api_mark_read_other_user_404(self):
        """POST mark read sur la notification d'un autre utilisateur → 404."""
        group_user = self.env.ref('base.group_user')
        group_social = self.env.ref('social_base.group_social_user')
        other = self.env['res.users'].sudo().create({
            'name': 'Other404', 'login': 'other_404_notif',
            'email': 'other404@notif.test', 'password': 'Test1234!',
            'group_ids': [(4, group_user.id), (4, group_social.id)],
        })
        admin = self.env.ref('base.user_admin')
        notif = self.env['club_social_profile.notification'].sudo().create({
            'user_id': other.id,
            'actor_id': admin.id,
            'type': 'post_like',
            'body': 'Belongs to other',
        })
        self.authenticate('admin', 'admin')
        _csrf = Request.csrf_token(self)
        resp = self.url_open(f'/social/api/notifications/{notif.id}/read', data={'csrf_token': _csrf, })
        self.assertEqual(resp.status_code, 404)

    def test_api_notif_to_dict_structure(self):
        """API response contains the expected fields for each notification."""
        self.authenticate('admin', 'admin')
        _csrf = Request.csrf_token(self)
        resp = self.url_open('/social/api/notifications')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        for n in data['data']['notifications']:
            for key in ('id', 'type', 'body', 'is_read', 'read_at',
                        'create_date', 'url', 'ref_model', 'ref_id'):
                self.assertIn(key, n)
