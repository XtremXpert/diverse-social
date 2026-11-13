"""Tests du modèle de rencontre (spontanée et planifiée)."""
import datetime

from odoo import fields
from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestSocialMeet(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.host = cls.env['res.users'].create({
            'name': 'Hôte Rencontre', 'login': 'host_meet@example.com'})
        cls.guest = cls.env['res.users'].create({
            'name': 'Invité Rencontre', 'login': 'guest_meet@example.com'})

    def _create_meet(self, **values):
        now = fields.Datetime.now()
        base = {
            'kind': 'now',
            'host_user_id': self.host.id,
            'date_start': now,
            'date_end': now + datetime.timedelta(hours=3),
            'audience': 'invited',
        }
        base.update(values)
        return self.env['social_meet.meet'].sudo().create(base)

    def _invite(self, meet, user, state='left'):
        return self.env['social_meet.participant'].sudo().create({
            'meet_id': meet.id, 'user_id': user.id, 'state': state})

    def test_now_open_with_host_participant(self):
        meet = self._create_meet()
        self.assertEqual(meet.state, 'open')
        self.assertEqual(meet.participant_count, 0)
        self.env['social_meet.participant'].sudo().create({
            'meet_id': meet.id, 'user_id': self.host.id, 'role': 'host'})
        self.assertEqual(meet.participant_count, 1)

    def test_now_duration_bounds(self):
        now = fields.Datetime.now()
        with self.assertRaises(ValidationError):
            self._create_meet(date_end=now + datetime.timedelta(hours=20))
        with self.assertRaises(ValidationError):
            self._create_meet(date_end=now + datetime.timedelta(minutes=10))

    def test_now_cannot_start_later(self):
        with self.assertRaises(ValidationError):
            self._create_meet(
                date_start=fields.Datetime.now() + datetime.timedelta(hours=2),
                date_end=fields.Datetime.now() + datetime.timedelta(hours=5))

    def test_planned_in_future(self):
        start = fields.Datetime.now() + datetime.timedelta(days=2)
        meet = self._create_meet(
            kind='planned', date_start=start,
            date_end=start + datetime.timedelta(hours=3),
            audience='connections')
        self.assertEqual(meet.kind, 'planned')
        past = fields.Datetime.now() - datetime.timedelta(days=2)
        with self.assertRaises(ValidationError):
            self._create_meet(
                kind='planned', date_start=past,
                date_end=past + datetime.timedelta(hours=3),
                audience='connections')

    def test_join_and_leave(self):
        meet = self._create_meet()
        self._invite(meet, self.guest)
        participant = meet._api_join(self.guest)
        self.assertEqual(participant.state, 'joined')
        self.assertEqual(meet.participant_count, 1)
        meet._api_leave(self.guest)
        self.assertEqual(participant.state, 'left')
        self.assertEqual(meet.participant_count, 0)

    def test_seats_fill_the_meet(self):
        meet = self._create_meet(seats_max=2)
        self.env['social_meet.participant'].sudo().create({
            'meet_id': meet.id, 'user_id': self.host.id, 'role': 'host'})
        self._invite(meet, self.guest)
        meet._api_join(self.guest)
        self.assertEqual(meet.state, 'full')
        third = self.env['res.users'].create({
            'name': 'Troisième', 'login': 'third_meet@example.com'})
        self._invite(meet, third)
        with self.assertRaises(ValidationError):
            meet._api_join(third)

    def test_cron_expires_past_window(self):
        meet = self._create_meet()
        past = fields.Datetime.now() - datetime.timedelta(hours=4)
        # Fenêtre entièrement passée, mais cohérente (fin après début) : la
        # contrainte SQL date_order reste satisfaite.
        self.env.cr.execute(
            "UPDATE social_meet_meet SET date_start = %s, date_end = %s WHERE id = %s",
            (past, past + datetime.timedelta(hours=3), meet.id))
        meet.invalidate_recordset()
        self.env['social_meet.meet']._cron_expire()
        self.assertEqual(meet.state, 'expired')

    def test_host_cannot_leave(self):
        meet = self._create_meet()
        self.env['social_meet.participant'].sudo().create({
            'meet_id': meet.id, 'user_id': self.host.id, 'role': 'host'})
        with self.assertRaises(ValidationError):
            meet._api_leave(self.host)

    def test_api_list_only_visible(self):
        meet = self._create_meet()  # audience « invités »
        self._invite(meet, self.guest)
        self.assertIn(meet, self.env['social_meet.meet']._api_list(self.host))
        self.assertIn(meet, self.env['social_meet.meet']._api_list(self.guest))
        stranger = self.env['res.users'].create({
            'name': 'Étranger', 'login': 'stranger_meet@example.com'})
        self.assertNotIn(meet, self.env['social_meet.meet']._api_list(stranger))

    def test_as_dict_flags(self):
        meet = self._create_meet()
        self.env['social_meet.participant'].sudo().create({
            'meet_id': meet.id, 'user_id': self.host.id, 'role': 'host'})
        data = meet._as_dict(self.host)
        self.assertEqual(data['kind'], 'now')
        self.assertTrue(data['is_host'])
        self.assertTrue(data['joined'])
        self.assertEqual(data['participant_count'], 1)
        self.assertEqual(len(data['participants']), 1)
        self.assertIsNone(data['event_id'])

    def test_publish_creates_event(self):
        start = fields.Datetime.now() + datetime.timedelta(days=3)
        meet = self._create_meet(
            kind='planned', date_start=start,
            date_end=start + datetime.timedelta(hours=3),
            audience='members', seats_max=6)
        event = meet._api_publish()
        self.assertEqual(meet.event_id, event)
        self.assertEqual(event.date_begin, meet.date_start)
        self.assertEqual(event.seats_max, 6)
        # idempotent : publier deux fois ne crée pas un second événement
        self.assertEqual(meet._api_publish(), event)

    def test_publish_refuses_now_meet(self):
        meet = self._create_meet()
        with self.assertRaises(ValidationError):
            meet._api_publish()

    def test_channel_created_once(self):
        meet = self._create_meet()
        channel = meet._create_channel()
        self.assertEqual(meet.channel_id, channel)
        self.assertIn(self.host.partner_id, channel.channel_member_ids.partner_id)
        self.assertEqual(meet._create_channel(), channel)

    def test_join_and_leave_move_channel_members(self):
        meet = self._create_meet()
        meet._create_channel()
        self._invite(meet, self.guest)
        meet._api_join(self.guest)
        self.assertIn(self.guest.partner_id, meet.channel_id.channel_member_ids.partner_id)
        meet._api_leave(self.guest)
        self.assertNotIn(self.guest.partner_id, meet.channel_id.channel_member_ids.partner_id)

    def test_expire_archives_channel(self):
        meet = self._create_meet()
        channel = meet._create_channel()
        past = fields.Datetime.now() - datetime.timedelta(hours=4)
        self.env.cr.execute(
            "UPDATE social_meet_meet SET date_start = %s, date_end = %s WHERE id = %s",
            (past, past + datetime.timedelta(hours=3), meet.id))
        meet.invalidate_recordset()
        self.env['social_meet.meet']._cron_expire()
        self.assertFalse(channel.active)
