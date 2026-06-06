from odoo.tests import TransactionCase, tagged


@tagged('social_notifications', 'discuss_hooks')
class TestDiscussNotif(TransactionCase):
    """Un message Discuss (chat 1:1) déclenche la notification réseau
    `new_message` chez le destinataire (et pas chez l'auteur)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        g_user = cls.env.ref('base.group_user')
        g_social = cls.env.ref('social_base.group_social_user')

        def mk(name, login):
            return cls.env['res.users'].create({
                'name': name, 'login': login, 'email': '%s@test.test' % login,
                'group_ids': [(4, g_user.id), (4, g_social.id)],
            })

        cls.alice = mk('DN Alice', 'dn_alice')
        cls.bob = mk('DN Bob', 'dn_bob')
        cls.Notif = cls.env['club_social_profile.notification']

    def _chat(self):
        return self.env['discuss.channel'].with_user(self.alice).sudo() \
            ._get_or_create_chat([self.bob.partner_id.id])

    def test_discuss_message_notifies_recipient(self):
        channel = self._chat()
        before = self.Notif.sudo().search_count(
            [('user_id', '=', self.bob.id), ('type', '=', 'new_message')])
        channel.with_user(self.alice).sudo().message_post(body='hi', message_type='comment')
        after = self.Notif.sudo().search_count(
            [('user_id', '=', self.bob.id), ('type', '=', 'new_message')])
        self.assertEqual(after, before + 1)

    def test_no_self_notification(self):
        channel = self._chat()
        channel.with_user(self.alice).sudo().message_post(body='hi', message_type='comment')
        self.assertEqual(self.Notif.sudo().search_count(
            [('user_id', '=', self.alice.id), ('type', '=', 'new_message')]), 0)

    def test_system_message_no_notification(self):
        channel = self._chat()
        before = self.Notif.sudo().search_count([('type', '=', 'new_message')])
        channel.with_user(self.alice).sudo().message_post(body='joined', message_type='notification')
        after = self.Notif.sudo().search_count([('type', '=', 'new_message')])
        self.assertEqual(after, before)
