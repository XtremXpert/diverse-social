from odoo.tests import TransactionCase, tagged
from odoo.exceptions import UserError


@tagged('social_messaging_discuss', 'post_install', '-at_install')
class TestBlockEnforcement(TransactionCase):
    """Le blocage social_safety doit être appliqué sur la messagerie Discuss :
    ni démarrage de chat, ni envoi de message entre personnes bloquées — y
    compris via le chemin réel (sudo, comme /mail/message/post). Et AUCUNE
    régression sur les canaux non-chat (équipes internes)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        group_user = cls.env.ref('base.group_user')
        group_social = cls.env.ref('social_base.group_social_user')

        def mk(name, login):
            return cls.env['res.users'].create({
                'name': name, 'login': login, 'email': '%s@test.test' % login,
                'group_ids': [(4, group_user.id), (4, group_social.id)],
            })

        cls.alice = mk('SMD Alice', 'smd_alice')
        cls.bob = mk('SMD Bob', 'smd_bob')
        cls.Channel = cls.env['discuss.channel']
        cls.Block = cls.env['social_safety.block']

    def _block(self, blocker, blocked):
        self.Block.sudo().create({
            'blocker_id': blocker.id, 'blocked_id': blocked.id,
        })

    def _chat_as(self, sender, other):
        """Crée/récupère le chat 1:1, comme le controller (sudo, env.user=sender)."""
        return self.Channel.with_user(sender).sudo()._get_or_create_chat(
            [other.partner_id.id])

    # ── _get_or_create_chat ──────────────────────────────────────────────────

    def test_get_or_create_chat_blocked_raises(self):
        self._block(self.alice, self.bob)
        with self.assertRaises(UserError):
            self.Channel.with_user(self.alice)._get_or_create_chat(
                [self.bob.partner_id.id])

    def test_get_or_create_chat_blocked_reverse(self):
        # Bob bloque Alice → Alice ne peut pas non plus démarrer (bidirectionnel).
        self._block(self.bob, self.alice)
        with self.assertRaises(UserError):
            self.Channel.with_user(self.alice)._get_or_create_chat(
                [self.bob.partner_id.id])

    def test_get_or_create_chat_not_blocked_ok(self):
        channel = self._chat_as(self.alice, self.bob)
        self.assertEqual(channel.channel_type, 'chat')
        self.assertIn(self.bob.partner_id, channel.channel_member_ids.partner_id)
        self.assertIn(self.alice.partner_id, channel.channel_member_ids.partner_id)

    # ── message_post ─────────────────────────────────────────────────────────

    def test_message_post_blocked_raises(self):
        channel = self._chat_as(self.alice, self.bob)
        self._block(self.alice, self.bob)
        with self.assertRaises(UserError):
            channel.with_user(self.alice).message_post(
                body='hello', message_type='comment')

    def test_message_post_blocked_raises_under_sudo(self):
        # Reproduit le chemin réel /mail/message/post : thread.sudo().message_post.
        # .sudo() ne change pas env.user → le blocage doit quand même lever.
        channel = self._chat_as(self.alice, self.bob)
        self._block(self.bob, self.alice)
        with self.assertRaises(UserError):
            channel.with_user(self.alice).sudo().message_post(
                body='hello', message_type='comment')

    def test_message_post_not_blocked_ok(self):
        channel = self._chat_as(self.alice, self.bob)
        msg = channel.with_user(self.alice).sudo().message_post(
            body='hi there', message_type='comment')
        self.assertTrue(msg)

    def test_message_post_system_message_not_blocked(self):
        # Les messages système (notification) ne doivent jamais lever, même bloqué.
        channel = self._chat_as(self.alice, self.bob)
        self._block(self.alice, self.bob)
        msg = channel.with_user(self.alice).sudo().message_post(
            body='X a rejoint', message_type='notification')
        self.assertTrue(msg)

    def test_internal_channel_not_affected(self):
        # Non-régression : un canal d'équipe ('channel') entre membres bloqués
        # n'est PAS soumis au blocage (scope strict chat 1:1).
        channel = self.Channel.sudo().create({
            'name': 'Internal Team', 'channel_type': 'channel',
        })
        channel.sudo()._add_members(
            partners=(self.alice.partner_id + self.bob.partner_id))
        self._block(self.alice, self.bob)
        # Ne doit PAS lever.
        msg = channel.with_user(self.alice).sudo().message_post(
            body='team message', message_type='comment')
        self.assertTrue(msg)
