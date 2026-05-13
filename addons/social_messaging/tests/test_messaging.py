from odoo.tests import TransactionCase, tagged
from odoo.exceptions import ValidationError


@tagged('social_messaging', 'messaging')
class TestSocialMessaging(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user1 = cls.env['res.users'].create({
            'name': 'Msg User 1', 'login': 'msg_test_user1', 'email': 'msg1@test.test',
        })
        cls.user2 = cls.env['res.users'].create({
            'name': 'Msg User 2', 'login': 'msg_test_user2', 'email': 'msg2@test.test',
        })
        cls.Thread = cls.env['social_messaging.thread']

    def test_get_or_create_thread(self):
        thread = self.Thread.sudo()._get_or_create([self.user1.id, self.user2.id])
        self.assertIn(self.user1, thread.participant_ids)
        self.assertIn(self.user2, thread.participant_ids)

    def test_get_or_create_idempotent(self):
        t1 = self.Thread.sudo()._get_or_create([self.user1.id, self.user2.id])
        t2 = self.Thread.sudo()._get_or_create([self.user1.id, self.user2.id])
        self.assertEqual(t1, t2)

    def test_thread_requires_two_participants(self):
        with self.assertRaises(ValidationError):
            self.Thread.create({'participant_ids': [(4, self.user1.id)]})

    def test_send_message(self):
        thread = self.Thread.sudo()._get_or_create([self.user1.id, self.user2.id])
        msg = self.env['social_messaging.message'].create({
            'thread_id': thread.id,
            'author_id': self.user1.id,
            'content': 'Hello!',
        })
        self.assertEqual(msg.author_id, self.user1)
        self.assertEqual(len(thread.message_ids), 1)

    def test_empty_message_raises(self):
        thread = self.Thread.sudo()._get_or_create([self.user1.id, self.user2.id])
        with self.assertRaises(ValidationError):
            self.env['social_messaging.message'].create({
                'thread_id': thread.id,
                'author_id': self.user1.id,
                'content': '   ',
            })

    def test_unread_count(self):
        thread = self.Thread.sudo()._get_or_create([self.user1.id, self.user2.id])
        self.env['social_messaging.message'].create({
            'thread_id': thread.id,
            'author_id': self.user1.id,
            'content': 'Unread',
        })
        self.assertEqual(thread.unread_count_for(self.user2), 1)

    def test_mark_as_read(self):
        thread = self.Thread.sudo()._get_or_create([self.user1.id, self.user2.id])
        msg = self.env['social_messaging.message'].create({
            'thread_id': thread.id,
            'author_id': self.user1.id,
            'content': 'Mark me',
        })
        msg.mark_as_read(self.user2)
        self.assertIn(self.user2, msg.read_by_ids)
        self.assertEqual(thread.unread_count_for(self.user2), 0)

    def test_last_message_preview(self):
        thread = self.Thread.sudo()._get_or_create([self.user1.id, self.user2.id])
        self.env['social_messaging.message'].create({
            'thread_id': thread.id,
            'author_id': self.user1.id,
            'content': 'Preview text',
        })
        self.assertEqual(thread.last_message_preview, 'Preview text')
