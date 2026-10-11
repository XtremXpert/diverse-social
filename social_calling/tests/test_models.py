"""
Tests for social_calling.session model.
Covers: creation, state transitions, blocking, group rooms, participants, cron.
"""

from odoo import fields
from odoo.tests import common
from odoo.exceptions import ValidationError, AccessDenied


class TestSocialCallingSession(common.TransactionCase):
    """Tests for social_calling.session model."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.user_alice = cls.env['res.users'].create({
            'name': 'Alice',
            'login': 'alice_call',
            'email': 'alice@test.com',
        })
        cls.user_bob = cls.env['res.users'].create({
            'name': 'Bob',
            'login': 'bob_call',
            'email': 'bob@test.com',
        })
        cls.user_charlie = cls.env['res.users'].create({
            'name': 'Charlie',
            'login': 'charlie_call',
            'email': 'charlie@test.com',
        })

    # ── Direct calls ───────────────────────────────────────────────────────

    def test_create_direct_call(self):
        """A direct call is created with default ringing state."""
        session = self.env['social_calling.session'].sudo().create({
            'caller_id': self.user_alice.id,
            'callee_id': self.user_bob.id,
            'call_type': 'video',
        })
        self.assertTrue(session.name.startswith('CALL-'))
        self.assertEqual(session.room_type, 'direct')
        self.assertEqual(session.state, 'ringing')
        self.assertTrue(session.room_name)
        self.assertTrue(session.room_password)

    def test_cannot_call_self(self):
        """A user cannot be caller and callee at the same time."""
        # Block check will catch this indirectly, but test the constraint
        with self.assertRaises(ValidationError):
            self.env['social_calling.session'].sudo().create({
                'caller_id': self.user_alice.id,
                'callee_id': self.user_alice.id,
                'call_type': 'video',
            })

    def test_blocked_call_prevented(self):
        """A call is prevented when users have blocked each other."""
        self.env['social_safety.block'].sudo().create({
            'blocker_id': self.user_alice.id,
            'blocked_id': self.user_bob.id,
        })
        with self.assertRaises(ValidationError) as cm:
            self.env['social_calling.session'].sudo().create({
                'caller_id': self.user_alice.id,
                'callee_id': self.user_bob.id,
                'call_type': 'video',
            })
        self.assertIn('blocked', str(cm.exception).lower())

    def test_action_connect(self):
        """Callee joining marks the call connected."""
        session = self.env['social_calling.session'].sudo().create({
            'caller_id': self.user_alice.id,
            'callee_id': self.user_bob.id,
            'call_type': 'video',
        })
        session.action_connect()
        self.assertEqual(session.state, 'connected')
        self.assertTrue(session.started_at)

    def test_action_connect_not_ringing_fails(self):
        """Cannot connect a call that is not ringing."""
        session = self.env['social_calling.session'].sudo().create({
            'caller_id': self.user_alice.id,
            'callee_id': self.user_bob.id,
            'call_type': 'video',
        })
        session.action_end()
        with self.assertRaises(ValidationError):
            session.action_connect()

    def test_action_end(self):
        """Ending a call sets state and ended_at."""
        session = self.env['social_calling.session'].sudo().create({
            'caller_id': self.user_alice.id,
            'callee_id': self.user_bob.id,
            'call_type': 'video',
        })
        session.action_connect()
        session.action_end()
        self.assertEqual(session.state, 'ended')
        self.assertTrue(session.ended_at)

    def test_action_decline(self):
        """Declining a call sets declined state."""
        session = self.env['social_calling.session'].sudo().create({
            'caller_id': self.user_alice.id,
            'callee_id': self.user_bob.id,
            'call_type': 'video',
        })
        session.action_decline()
        self.assertEqual(session.state, 'declined')

    def test_duration_computation(self):
        """Duration is computed from started_at to ended_at."""
        session = self.env['social_calling.session'].sudo().create({
            'caller_id': self.user_alice.id,
            'callee_id': self.user_bob.id,
            'call_type': 'video',
        })
        session.action_connect()
        session.ended_at = fields.Datetime.add(session.started_at, seconds=125)
        session._compute_duration()
        self.assertEqual(session.duration_seconds, 125)

    # ── Group rooms ────────────────────────────────────────────────────────

    def test_create_group_room(self):
        """A group room is created with host and participants."""
        session = self.env['social_calling.session'].sudo().create({
            'name': 'Test Room',
            'room_type': 'group',
            'host_id': self.user_alice.id,
            'call_type': 'video',
            'max_participants': 5,
        })
        self.assertEqual(session.room_type, 'group')
        self.assertEqual(session.host_id, self.user_alice)
        self.assertIn(self.user_alice.id, session.participant_ids.ids)
        self.assertEqual(session.max_participants, 5)

    def test_group_room_exceeds_max_participants(self):
        """Adding beyond max participants raises ValidationError."""
        session = self.env['social_calling.session'].sudo().create({
            'name': 'Small Room',
            'room_type': 'group',
            'host_id': self.user_alice.id,
            'call_type': 'audio',
            'max_participants': 2,
        })
        session.action_add_participant(self.user_bob.id)
        with self.assertRaises(ValidationError) as cm:
            session.action_add_participant(self.user_charlie.id)
        self.assertIn('full', str(cm.exception).lower())

    def test_group_room_add_remove_participant(self):
        """Host can add and remove participants."""
        session = self.env['social_calling.session'].sudo().create({
            'name': 'Room',
            'room_type': 'group',
            'host_id': self.user_alice.id,
            'call_type': 'video',
            'max_participants': 5,
        })
        session.action_add_participant(self.user_bob.id)
        self.assertIn(self.user_bob.id, session.participant_ids.ids)

        session.action_remove_participant(self.user_bob.id)
        self.assertNotIn(self.user_bob.id, session.participant_ids.ids)

    def test_group_room_empty_ends(self):
        """Removing last participant ends the room."""
        session = self.env['social_calling.session'].sudo().create({
            'name': 'Room',
            'room_type': 'group',
            'host_id': self.user_alice.id,
            'call_type': 'video',
            'state': 'connected',
            'started_at': fields.Datetime.now(),
        })
        session.action_remove_participant(self.user_alice.id)
        self.assertEqual(session.state, 'ended')

    def test_blocked_user_cannot_join_group(self):
        """A blocked user cannot be added to a group room."""
        self.env['social_safety.block'].sudo().create({
            'blocker_id': self.user_alice.id,
            'blocked_id': self.user_bob.id,
        })
        session = self.env['social_calling.session'].sudo().create({
            'name': 'Room',
            'room_type': 'group',
            'host_id': self.user_alice.id,
            'call_type': 'video',
        })
        with self.assertRaises(ValidationError) as cm:
            session.action_add_participant(self.user_bob.id)
        self.assertIn('blocked', str(cm.exception).lower())

    # ── Cron ───────────────────────────────────────────────────────────────

    def test_cron_mark_missed_calls(self):
        """Cron marks ringing calls older than 2 minutes as missed."""
        session = self.env['social_calling.session'].sudo().create({
            'caller_id': self.user_alice.id,
            'callee_id': self.user_bob.id,
            'call_type': 'video',
        })
        # Artificially backdate: Odoo 20 ignores ORM writes on create_date
        self.env.flush_all()
        self.env.cr.execute(
            "UPDATE social_calling_session SET create_date = %s WHERE id = %s",
            (fields.Datetime.add(fields.Datetime.now(), minutes=-5), session.id),
        )
        session.invalidate_recordset(['create_date'])

        count = self.env['social_calling.session'].cron_mark_missed_calls()
        self.assertEqual(count, 1)
        self.assertEqual(session.state, 'missed')

    def test_cron_does_not_mark_recent_calls(self):
        """Recent ringing calls are not marked missed."""
        session = self.env['social_calling.session'].sudo().create({
            'caller_id': self.user_alice.id,
            'callee_id': self.user_bob.id,
            'call_type': 'video',
        })
        count = self.env['social_calling.session'].cron_mark_missed_calls()
        self.assertEqual(count, 0)
        self.assertEqual(session.state, 'ringing')

    # ── Access / Security ────────────────────────────────────────────────

    def test_non_admin_cannot_spoof_caller(self):
        """A non-admin user cannot create a call with another user as caller."""
        with self.assertRaises(AccessDenied):
            self.env['social_calling.session'].with_user(self.user_bob).create({
                'caller_id': self.user_alice.id,
                'callee_id': self.user_charlie.id,
                'call_type': 'video',
            })

    def test_admin_can_create_for_any_caller(self):
        """Admin can create calls on behalf of others."""
        admin = self.env.ref('base.user_admin')
        session = self.env['social_calling.session'].with_user(admin).create({
            'caller_id': self.user_alice.id,
            'callee_id': self.user_bob.id,
            'call_type': 'video',
        })
        self.assertTrue(session.exists())
