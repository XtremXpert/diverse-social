import json
from datetime import timedelta

from odoo import fields
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestCallEndAlone(TransactionCase):
    """Un appel qui n'a jamais impliqué plus de deux personnes se termine quand il n'en reste qu'une."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Pas de SFU : l'appel reste entre Odoo et les navigateurs.
        cls.env['ir.config_parameter'].sudo().search([('key', '=', 'mail.sfu_server_url')]).unlink()
        Users = cls.env['res.users'].with_context(no_reset_password=True)
        cls.a, cls.b, cls.c = (Users.create({
            'name': name, 'login': f'call-alone-{name}@example.com',
            'group_ids': [(6, 0, [cls.env.ref('base.group_user').id])],
        }) for name in ('A', 'B', 'C'))
        cls.chat = cls.env['discuss.channel'].with_user(cls.a)._get_or_create_chat([cls.b.partner_id.id])
        cls.group = cls.env['discuss.channel'].with_user(cls.a)._create_group(users_to=cls.b | cls.c)

    def member(self, channel, user):
        return channel.channel_member_ids.filtered(lambda m: m.partner_id == user.partner_id).with_user(user).sudo()

    def join(self, channel, user):
        self.member(channel, user)._rtc_join_call()

    def leave(self, channel, user):
        self.member(channel, user)._rtc_leave_call()

    def in_call(self, channel):
        return channel.sudo().rtc_session_ids.partner_id

    def test_other_hangs_up_ends_two_person_call(self):
        self.join(self.chat, self.a)
        self.join(self.chat, self.b)
        self.assertEqual(self.in_call(self.chat), (self.a | self.b).partner_id, "répondre ne coupe personne")
        self.leave(self.chat, self.b)
        self.assertFalse(self.in_call(self.chat), "A n'attend plus personne : son appel se termine")
        history = self.env['discuss.call.history'].search([('channel_id', '=', self.chat.id)], limit=1)
        self.assertTrue(history.end_dt, "l'appel est terminé dans l'historique")
        self.assertEqual(len(history.involved_member_ids), 2)

    def test_decline_ends_two_person_call(self):
        self.join(self.chat, self.a)
        self.assertTrue(self.member(self.chat, self.b).rtc_inviting_session_id, "B est invité")
        self.leave(self.chat, self.b)  # refuser : pas de session, l'invitation est annulée
        self.assertFalse(self.in_call(self.chat))

    def test_switching_device_keeps_call(self):
        self.join(self.chat, self.a)
        self.join(self.chat, self.b)
        self.join(self.chat, self.a)  # A reprend l'appel sur un autre appareil
        self.assertEqual(self.in_call(self.chat), (self.a | self.b).partner_id)

    def test_alone_caller_waits_while_ringing(self):
        self.join(self.chat, self.a)
        self.assertEqual(self.in_call(self.chat), self.a.partner_id, "seul, mais B est encore invité")

    def test_group_call_keeps_last_person(self):
        self.join(self.group, self.a)
        self.join(self.group, self.b)
        self.leave(self.group, self.c)
        self.leave(self.group, self.b)
        self.assertEqual(self.in_call(self.group), self.a.partner_id,
                         "trois personnes impliquées : la dernière n'est pas raccrochée")

    def bus_payloads(self, notification_type):
        self.env.cr.precommit.run()
        messages = [json.loads(m) for m in self.env['bus.bus'].sudo().search([]).mapped('message')]
        return [m['payload'] for m in messages if m['type'] == notification_type]

    def test_group_call_asks_last_person(self):
        self.join(self.group, self.a)
        self.join(self.group, self.b)
        self.leave(self.group, self.c)
        session_a = self.member(self.group, self.a).rtc_session_ids
        self.assertFalse(self.group._social_call_alone_prompt(session_a), "B est encore là")
        self.bus_payloads('social_calling_discuss/alone')
        self.env['bus.bus'].sudo().search([]).unlink()
        self.leave(self.group, self.b)
        self.assertEqual(self.bus_payloads('social_calling_discuss/alone'),
                         [{'sessionId': session_a.id, 'channelId': self.group.id, 'timeout': 30}])
        self.assertTrue(self.group._social_call_alone_prompt(session_a))
        self.assertEqual(self.group._social_call_involved_count(), 3)

    def test_two_person_call_never_asks(self):
        self.join(self.chat, self.a)
        self.join(self.chat, self.b)
        self.env.cr.precommit.run()
        self.env['bus.bus'].sudo().search([]).unlink()
        self.leave(self.chat, self.b)
        self.assertEqual(self.bus_payloads('social_calling_discuss/alone'), [])

    def test_expired_session_ends_two_person_call(self):
        self.join(self.chat, self.a)
        self.join(self.chat, self.b)
        session_b = self.member(self.chat, self.b).rtc_session_ids
        self.env.flush_all()
        self.env.cr.execute("UPDATE discuss_channel_rtc_session SET write_date = %s WHERE id = %s",
                            (fields.Datetime.now() - timedelta(minutes=5), session_b.id))
        self.env.invalidate_all()
        self.env['discuss.channel.rtc.session'].sudo()._gc_inactive_sessions()
        self.assertFalse(self.in_call(self.chat))

    def test_site_is_told_the_call_ended_normally(self):
        self.join(self.chat, self.a)
        session_a = self.member(self.chat, self.a).rtc_session_ids
        self.env.cr.precommit.run()
        self.env['bus.bus'].sudo().search([]).unlink()
        self.leave(self.chat, self.b)
        self.assertEqual(self.bus_payloads('social_calling_discuss/ended_alone'), [{'sessionId': session_a.id}])
