from odoo.tests import TransactionCase, tagged


@tagged('social_privacy', 'discuss_privacy')
class TestDiscussPrivacy(TransactionCase):
    """Loi 25 : les messages Discuss (chat 1:1) doivent être exportés et
    supprimés lors de l'anonymisation, comme l'étaient les social_messaging."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.alice = cls.env['res.users'].create({
            'name': 'DP Alice', 'login': 'dp_alice', 'email': 'dp_alice@test.test',
        })
        cls.bob = cls.env['res.users'].create({
            'name': 'DP Bob', 'login': 'dp_bob', 'email': 'dp_bob@test.test',
        })
        cls.channel = cls.env['discuss.channel'].with_user(cls.alice).sudo() \
            ._get_or_create_chat([cls.bob.partner_id.id])
        cls.dmsg = cls.channel.with_user(cls.alice).sudo().message_post(
            body='Bonjour Bob', message_type='comment')

    def test_export_includes_discuss_messages(self):
        data = self.env['social_privacy.export_request']._gather_personal_data(self.alice)
        self.assertIn('discuss_messages', data)
        ids = [m['id'] for m in data['discuss_messages']]
        self.assertIn(self.dmsg.id, ids)

    def test_anonymize_deletes_discuss_messages(self):
        wizard = self.env['social_privacy.anonymize_wizard'].create(
            {'partner_id': self.alice.partner_id.id})
        msg_id = self.dmsg.id
        wizard._anonymize_messages(self.alice)
        self.assertFalse(self.env['mail.message'].sudo().browse(msg_id).exists())
        log = self.env['social_privacy.access_log'].sudo().search([
            ('model_name', '=', 'discuss.channel'),
            ('action', '=', 'delete'),
            ('target_user_id', '=', self.alice.id),
        ], limit=1)
        self.assertTrue(log)
