from odoo.tests import TransactionCase, tagged
from odoo.exceptions import UserError, ValidationError


@tagged('social_messaging', 'messaging')
class TestSocialMessaging(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        group_user = cls.env.ref('base.group_user')
        group_social = cls.env.ref('social_base.group_social_user')
        cls.user1 = cls.env['res.users'].create({
            'name': 'Msg User 1', 'login': 'msg_test_user1', 'email': 'msg1@test.test',
            'group_ids': [(4, group_user.id), (4, group_social.id)],
        })
        cls.user2 = cls.env['res.users'].create({
            'name': 'Msg User 2', 'login': 'msg_test_user2', 'email': 'msg2@test.test',
            'group_ids': [(4, group_user.id), (4, group_social.id)],
        })
        cls.user3 = cls.env['res.users'].create({
            'name': 'Msg User 3', 'login': 'msg_test_user3', 'email': 'msg3@test.test',
            'group_ids': [(4, group_user.id), (4, group_social.id)],
        })
        cls.Thread = cls.env['social_messaging.thread']
        cls.Block = cls.env['social_safety.block']

    # ── Thread creation ───────────────────────────────────────────────────────

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

    # ── Block enforcement: thread creation ───────────────────────────────────

    def test_blocked_user_cannot_start_thread(self):
        self.Block.with_user(self.user1).block_user(self.user2)
        try:
            with self.assertRaises(UserError):
                self.Thread.sudo()._get_or_create([self.user1.id, self.user2.id])
        finally:
            self.Block.with_user(self.user1).unblock_user(self.user2)

    def test_reverse_block_also_prevents_thread(self):
        self.Block.with_user(self.user2).block_user(self.user1)
        try:
            with self.assertRaises(UserError):
                self.Thread.sudo()._get_or_create([self.user1.id, self.user2.id])
        finally:
            self.Block.with_user(self.user2).unblock_user(self.user1)

    def test_unblocked_users_can_create_thread(self):
        thread = self.Thread.sudo()._get_or_create([self.user1.id, self.user3.id])
        self.assertIn(self.user1, thread.participant_ids)
        self.assertIn(self.user3, thread.participant_ids)

    # ── Block enforcement: message sending ───────────────────────────────────

    def test_blocked_user_cannot_send_message(self):
        thread = self.Thread.sudo()._get_or_create([self.user1.id, self.user2.id])
        self.Block.with_user(self.user1).block_user(self.user2)
        try:
            with self.assertRaises(UserError):
                self.env['social_messaging.message'].sudo().create({
                    'thread_id': thread.id,
                    'author_id': self.user1.id,
                    'content': 'Should be blocked',
                })
        finally:
            self.Block.with_user(self.user1).unblock_user(self.user2)

    # ── Messaging ─────────────────────────────────────────────────────────────

    def test_send_message(self):
        thread = self.Thread.sudo()._get_or_create([self.user1.id, self.user2.id])
        msg = self.env['social_messaging.message'].sudo().create({
            'thread_id': thread.id,
            'author_id': self.user1.id,
            'content': 'Hello!',
        })
        self.assertEqual(msg.author_id, self.user1)
        self.assertEqual(len(thread.message_ids), 1)

    def test_blank_content_allowed_at_model_level(self):
        """The model no longer enforces a non-blank content constraint —
        messages can be attachment-only. The "empty message" check moved
        to the controllers, which reject `not content and not files` at
        the request boundary."""
        thread = self.Thread.sudo()._get_or_create([self.user1.id, self.user2.id])
        msg = self.env['social_messaging.message'].sudo().create({
            'thread_id': thread.id,
            'author_id': self.user1.id,
            'content': '   ',
        })
        self.assertTrue(msg)

    def test_unread_count(self):
        thread = self.Thread.sudo()._get_or_create([self.user1.id, self.user2.id])
        self.env['social_messaging.message'].sudo().create({
            'thread_id': thread.id,
            'author_id': self.user1.id,
            'content': 'Unread',
        })
        self.assertEqual(thread.unread_count_for(self.user2), 1)

    def test_mark_as_read(self):
        thread = self.Thread.sudo()._get_or_create([self.user1.id, self.user2.id])
        msg = self.env['social_messaging.message'].sudo().create({
            'thread_id': thread.id,
            'author_id': self.user1.id,
            'content': 'Mark me',
        })
        msg.mark_as_read(self.user2)
        self.assertIn(self.user2, msg.read_by_ids)
        self.assertEqual(thread.unread_count_for(self.user2), 0)

    def test_last_message_preview(self):
        thread = self.Thread.sudo()._get_or_create([self.user1.id, self.user2.id])
        self.env['social_messaging.message'].sudo().create({
            'thread_id': thread.id,
            'author_id': self.user1.id,
            'content': 'Preview text',
        })
        self.assertEqual(thread.last_message_preview, 'Preview text')

    def test_other_participant(self):
        thread = self.Thread.sudo()._get_or_create([self.user1.id, self.user2.id])
        self.assertEqual(thread.other_participant(self.user1), self.user2)

    # ── Record rule: participants only ────────────────────────────────────────

    def test_participant_can_read_thread(self):
        thread = self.Thread.sudo()._get_or_create([self.user1.id, self.user2.id])
        found = self.Thread.with_user(self.user1).search([('id', '=', thread.id)])
        self.assertTrue(found)

    def test_outsider_cannot_read_thread(self):
        thread = self.Thread.sudo()._get_or_create([self.user1.id, self.user2.id])
        found = self.Thread.with_user(self.user3).search([('id', '=', thread.id)])
        self.assertFalse(found)

    # ── Additional block tests ────────────────────────────────────────────────

    def test_reverse_block_prevents_send(self):
        """Si user2 bloque user1, user1 ne peut pas envoyer de message."""
        thread = self.Thread.sudo()._get_or_create([self.user1.id, self.user2.id])
        self.Block.with_user(self.user2).block_user(self.user1)
        try:
            with self.assertRaises(UserError):
                self.env['social_messaging.message'].sudo().create({
                    'thread_id': thread.id,
                    'author_id': self.user1.id,
                    'content': 'Should be blocked by reverse',
                })
        finally:
            self.Block.with_user(self.user2).unblock_user(self.user1)

    def test_group_thread_block_not_checked(self):
        """A 3-participant thread is not blocked even if two participants block each other."""
        thread = self.Thread.sudo().create({
            'participant_ids': [(6, 0, [self.user1.id, self.user2.id, self.user3.id])],
        })
        self.Block.with_user(self.user1).block_user(self.user2)
        try:
            msg = self.env['social_messaging.message'].sudo().create({
                'thread_id': thread.id,
                'author_id': self.user1.id,
                'content': 'Group message despite block',
            })
            self.assertTrue(msg)
        finally:
            self.Block.with_user(self.user1).unblock_user(self.user2)

    # ── Computed ──────────────────────────────────────────────────────────────

    def test_last_message_date_updated(self):
        thread = self.Thread.sudo()._get_or_create([self.user1.id, self.user2.id])
        self.env['social_messaging.message'].sudo().create({
            'thread_id': thread.id, 'author_id': self.user1.id, 'content': 'Hello',
        })
        self.assertTrue(thread.last_message_date)

    def test_preview_truncated_at_80_chars(self):
        thread = self.Thread.sudo()._get_or_create([self.user1.id, self.user2.id])
        long_content = 'A' * 100
        self.env['social_messaging.message'].sudo().create({
            'thread_id': thread.id, 'author_id': self.user1.id, 'content': long_content,
        })
        self.assertLessEqual(len(thread.last_message_preview), 80)

    def test_author_unread_count_zero(self):
        """Messages sent by user1 don't count as unread for user1."""
        thread = self.Thread.sudo()._get_or_create([self.user1.id, self.user2.id])
        self.env['social_messaging.message'].sudo().create({
            'thread_id': thread.id, 'author_id': self.user1.id, 'content': 'My message',
        })
        self.assertEqual(thread.unread_count_for(self.user1), 0)
