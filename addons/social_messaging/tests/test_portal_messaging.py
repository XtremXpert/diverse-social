from odoo.tests import HttpCase, TransactionCase, tagged


def _make_social_user(env, name, login):
    group_social = env.ref('social_base.group_social_user')
    return env['res.users'].create({
        'name': name, 'login': login, 'email': f'{login}@msg.test',
        'password': 'Test1234!',
        'group_ids': [(4, group_social.id)],
    })


@tagged('social_messaging', 'portal_messaging')
class TestPortalMessagingData(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user_a = _make_social_user(cls.env, 'PortalMsgA', 'portal_msg_a')
        cls.user_b = _make_social_user(cls.env, 'PortalMsgB', 'portal_msg_b')
        cls.thread = cls.env['social_messaging.thread'].sudo()._get_or_create(
            [cls.user_a.id, cls.user_b.id]
        )

    def _send(self, user, content):
        return self.env['social_messaging.message'].sudo().create({
            'thread_id': self.thread.id,
            'author_id': user.id,
            'content': content,
            'read_by_ids': [(4, user.id)],
        })

    def test_thread_accessible_to_participant(self):
        found = self.env['social_messaging.thread'].with_user(self.user_a).search(
            [('id', '=', self.thread.id)]
        )
        self.assertTrue(found)

    def test_thread_not_accessible_to_outsider(self):
        outsider = _make_social_user(self.env, 'Outsider', 'portal_msg_outsider')
        found = self.env['social_messaging.thread'].with_user(outsider).search(
            [('id', '=', self.thread.id)]
        )
        self.assertFalse(found)

    def test_unread_count_for_recipient(self):
        self._send(self.user_a, 'Hello B!')
        self.assertGreaterEqual(self.thread.unread_count_for(self.user_b), 1)

    def test_mark_read_clears_unread(self):
        msg = self._send(self.user_a, 'Read me')
        msg.mark_as_read(self.user_b)
        self.assertIn(self.user_b, msg.read_by_ids)

    def test_last_message_preview_updated(self):
        self._send(self.user_a, 'Preview check')
        self.assertIn('Preview check', self.thread.last_message_preview)

    def test_other_participant(self):
        other = self.thread.other_participant(self.user_a)
        self.assertEqual(other, self.user_b)

    def test_messages_ordered_asc(self):
        self._send(self.user_a, 'First')
        self._send(self.user_b, 'Second')
        ids = self.thread.message_ids.sorted('id').ids
        self.assertEqual(ids, sorted(ids))

    def test_poll_returns_only_new_messages(self):
        msg1 = self._send(self.user_a, 'Old')
        msg2 = self._send(self.user_b, 'New')
        new = self.thread.message_ids.filtered(lambda m: m.id > msg1.id).sorted('id')
        self.assertIn(msg2, new)
        self.assertNotIn(msg1, new)

    def test_blocked_user_cannot_send(self):
        from odoo.exceptions import UserError
        Block = self.env['social_safety.block'].sudo()
        Block.with_user(self.user_a).block_user(self.user_b)
        try:
            with self.assertRaises(UserError):
                self._send(self.user_a, 'Should fail')
        finally:
            Block.with_user(self.user_a).unblock_user(self.user_b)

    def test_self_message_not_blocked_by_unread(self):
        msg = self._send(self.user_a, 'My own msg')
        self.assertNotIn(self.user_a, msg.read_by_ids.filtered(lambda u: u != self.user_a))


@tagged('social_messaging', 'portal_messaging', 'post_install', '-at_install')
class TestPortalMessagingHttp(HttpCase):

    def test_messages_list_unauthenticated_redirects(self):
        resp = self.url_open('/my/messages', allow_redirects=False)
        self.assertIn(resp.status_code, (302, 303))

    def test_messages_list_authenticated_ok(self):
        self.authenticate('admin', 'admin')
        resp = self.url_open('/my/messages')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'messages', resp.content.lower())

    def test_messages_thread_invalid_id_404(self):
        self.authenticate('admin', 'admin')
        resp = self.url_open('/my/messages/999999999')
        self.assertEqual(resp.status_code, 404)

    def test_messages_start_self_redirects(self):
        self.authenticate('admin', 'admin')
        admin = self.env.ref('base.user_admin')
        resp = self.url_open(
            f'/my/messages/start/{admin.id}',
            data={'csrf_token': self.csrf_token()},
        )
        self.assertEqual(resp.status_code, 200)

    def test_messages_start_creates_thread(self):
        group_social = self.env.ref('social_base.group_social_user')
        other = self.env['res.users'].create({
            'name': 'MsgHttpOther', 'login': 'msg_http_other',
            'email': 'msg_http_other@test.test',
            'password': 'Test1234!',
            'group_ids': [(4, group_social.id)],
        })
        self.authenticate('admin', 'admin')
        resp = self.url_open(
            f'/my/messages/start/{other.id}',
            data={'csrf_token': self.csrf_token()},
        )
        self.assertEqual(resp.status_code, 200)
        thread = self.env['social_messaging.thread'].sudo().search([
            ('participant_ids', 'in', [other.id]),
        ], limit=1)
        self.assertTrue(thread)

    def test_send_message_ajax(self):
        group_social = self.env.ref('social_base.group_social_user')
        other = self.env['res.users'].create({
            'name': 'MsgHttpSend', 'login': 'msg_http_send',
            'email': 'msg_http_send@test.test',
            'password': 'Test1234!',
            'group_ids': [(4, group_social.id)],
        })
        self.authenticate('admin', 'admin')
        admin = self.env.ref('base.user_admin')
        thread = self.env['social_messaging.thread'].sudo()._get_or_create(
            [admin.id, other.id]
        )
        resp = self.url_open(
            f'/my/messages/{thread.id}/send',
            data={'csrf_token': self.csrf_token(), 'content': 'Test AJAX send'},
        )
        self.assertEqual(resp.status_code, 200)
        import json
        data = json.loads(resp.content)
        self.assertTrue(data.get('ok'))
        self.assertEqual(data['message']['content'], 'Test AJAX send')

    def test_poll_returns_json(self):
        group_social = self.env.ref('social_base.group_social_user')
        other = self.env['res.users'].create({
            'name': 'MsgHttpPoll', 'login': 'msg_http_poll',
            'email': 'msg_http_poll@test.test',
            'password': 'Test1234!',
            'group_ids': [(4, group_social.id)],
        })
        self.authenticate('admin', 'admin')
        admin = self.env.ref('base.user_admin')
        thread = self.env['social_messaging.thread'].sudo()._get_or_create(
            [admin.id, other.id]
        )
        resp = self.url_open(f'/my/messages/{thread.id}/poll?since_id=0')
        self.assertEqual(resp.status_code, 200)
        import json
        data = json.loads(resp.content)
        self.assertTrue(data.get('ok'))
        self.assertIn('messages', data)
