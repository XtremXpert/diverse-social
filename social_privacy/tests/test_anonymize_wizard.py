from odoo.tests import TransactionCase, tagged


@tagged('social_privacy', 'anonymize')
class TestAnonymizeWizard(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.test_user = cls.env['res.users'].create({
            'name': 'Anon User',
            'login': 'anon_user',
            'email': 'anon@test.test',
        })
        cls.other_user = cls.env['res.users'].create({
            'name': 'Anon Peer',
            'login': 'anon_peer',
            'email': 'anon_peer@test.test',
        })
        cls.partner = cls.test_user.partner_id
        # Create a profile
        cls.user_profile = cls.env['club_social_profile.profile'].sudo().create({
            'user_id': cls.test_user.id,
            'bio': 'I am a test user',
            'city': 'Testville',
        })
        # Create a post
        cls.post = cls.env['social_base.post'].sudo().create({
            'author_id': cls.test_user.id,
            'content': 'Hello world',
        })
        # Create a Discuss chat message (messagerie migrée vers discuss.channel)
        cls.channel = cls.env['discuss.channel'].with_user(cls.test_user).sudo() \
            ._get_or_create_chat([cls.other_user.partner_id.id])
        cls.msg = cls.channel.with_user(cls.test_user).sudo().message_post(
            body='Test message', message_type='comment')

    def test_anonymize_wizard_counts(self):
        wizard = self.env['social_privacy.anonymize_wizard'].create({
            'partner_id': self.partner.id,
        })
        self.assertEqual(wizard.user_id, self.test_user)
        self.assertEqual(wizard.post_count, 1)
        self.assertEqual(wizard.message_count, 1)

    def test_anonymize_wizard_requires_confirm(self):
        wizard = self.env['social_privacy.anonymize_wizard'].create({
            'partner_id': self.partner.id,
        })
        with self.assertRaises(Exception):
            wizard.action_anonymize()

    def test_anonymize_wizard_execution(self):
        wizard = self.env['social_privacy.anonymize_wizard'].create({
            'partner_id': self.partner.id,
            'confirm_understand': True,
        })
        # Before anonymization
        posts_before = self.env['social_base.post'].sudo().search_count([
            ('author_id', '=', self.test_user.id)
        ])
        self.assertEqual(posts_before, 1)

        wizard.action_anonymize()

        # After anonymization: posts author_id cleared
        posts_after = self.env['social_base.post'].sudo().search_count([
            ('author_id', '=', self.test_user.id)
        ])
        self.assertEqual(posts_after, 0)

        # Profile bio cleared
        self.user_profile.invalidate_recordset()
        self.assertFalse(self.user_profile.bio)
        self.assertFalse(self.user_profile.city)

        # Messages Discuss deleted (most sensitive)
        chat_ids = self.env['discuss.channel'].sudo().search(
            [('channel_type', '=', 'chat')]).ids
        msgs_after = self.env['mail.message'].sudo().search_count([
            ('model', '=', 'discuss.channel'),
            ('res_id', 'in', chat_ids),
            ('author_id', '=', self.test_user.partner_id.id),
        ]) if chat_ids else 0
        self.assertEqual(msgs_after, 0)

        # Anonymization log created
        log = self.env['social_privacy.access_log'].sudo().search([
            ('target_user_id', '=', self.test_user.id),
            ('action', '=', 'anonymize'),
        ], limit=1)
        self.assertTrue(log)
