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
        with self.assertRaises(ValidationError):
            self._create_meet(
                kind='planned', date_start=start,
                date_end=start - datetime.timedelta(hours=1),
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
        self.env.cr.execute(
            "UPDATE social_meet_meet SET date_end = %s WHERE id = %s",
            (fields.Datetime.now() - datetime.timedelta(hours=1), meet.id))
        meet.invalidate_recordset()
        self.env['social_meet.meet']._cron_expire()
        self.assertEqual(meet.state, 'expired')

    def test_host_cannot_leave(self):
        meet = self._create_meet()
        self.env['social_meet.participant'].sudo().create({
            'meet_id': meet.id, 'user_id': self.host.id, 'role': 'host'})
        with self.assertRaises(ValidationError):
            meet._api_leave(self.host)
