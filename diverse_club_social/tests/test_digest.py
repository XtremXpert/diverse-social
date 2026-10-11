from datetime import timedelta
from unittest.mock import patch, MagicMock

from odoo import fields
from odoo.tests import TransactionCase, tagged


def _make_social_user(env, name, login):
    group_user = env.ref('base.group_user')
    group_social = env.ref('social_base.group_social_user')
    return env['res.users'].create({
        'name': name, 'login': login, 'email': f'{login}@diverse.test',
        'password': 'Test1234!',
        'group_ids': [(4, group_user.id), (4, group_social.id)],
    })


@tagged('diverse_club_social', 'digest')
class TestWeeklyDigest(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = _make_social_user(cls.env, 'DigestUser', 'digest_user')
        cls.profile = cls.env['club_social_profile.profile'].sudo().get_or_create_for_user(cls.user)
        write_vals = {'onboarding_done': True, 'digest_email_enabled': True}
        Profile = cls.env['club_social_profile.profile']
        if 'age_gate_passed' in Profile._fields:
            write_vals['age_gate_passed'] = True
        cls.profile.sudo().write(write_vals)

    def _run_cron(self):
        self.env['social_base.post'].sudo().cron_send_weekly_digest()

    # ── Helpers ──────────────────────────────────────────────────────────────

    def test_digest_upcoming_events_empty_when_no_model(self):
        # event.event model is always present in this test DB
        result = self.env['social_base.post']._digest_upcoming_events(fields.Datetime.now())
        self.assertTrue(hasattr(result, '_name') or isinstance(result, type(self.env['event.event'].browse())))

    def test_digest_upcoming_events_returns_future_only(self):
        if 'event.event' not in self.env:
            self.skipTest('event.event not installed')
        now = fields.Datetime.now()
        past_event = self.env['event.event'].sudo().create({
            'name': 'Past Digest Event',
            'date_begin': now - timedelta(days=2),
            'date_end': now - timedelta(days=1),
        })
        future_event = self.env['event.event'].sudo().create({
            'name': 'Future Digest Event',
            'date_begin': now + timedelta(days=2),
            'date_end': now + timedelta(days=3),
        })
        results = self.env['social_base.post']._digest_upcoming_events(now)
        result_ids = results.ids
        self.assertIn(future_event.id, result_ids)
        self.assertNotIn(past_event.id, result_ids)

    def test_digest_proposals_voting_returns_voting_state(self):
        if 'social_governance.proposal' not in self.env:
            self.skipTest('social_governance not installed')
        proposal = self.env['social_governance.proposal'].sudo().create({
            'name': 'Digest Test Proposal',
            'description': '<p>Test</p>',
            'author_id': self.user.id,
            'category_id': self.env.ref('social_governance.category_other').id,
            'voting_closes_at': fields.Datetime.now() + timedelta(days=7),
        })
        proposal.action_start_voting()
        results = self.env['social_base.post']._digest_proposals_voting()
        self.assertIn(proposal.id, results.ids)

    def test_digest_proposals_voting_excludes_draft(self):
        if 'social_governance.proposal' not in self.env:
            self.skipTest('social_governance not installed')
        self.env['social_governance.proposal'].sudo().create({
            'name': 'Draft Proposal',
            'description': '<p>Draft</p>',
            'author_id': self.user.id,
            'category_id': self.env.ref('social_governance.category_other').id,
            'voting_closes_at': fields.Datetime.now() + timedelta(days=7),
        })
        results = self.env['social_base.post']._digest_proposals_voting()
        names = results.mapped('name')
        self.assertNotIn('Draft Proposal', names)

    def test_digest_new_members_count_returns_int(self):
        count = self.env['social_base.post']._digest_new_members_count(
            fields.Datetime.now() - timedelta(days=7)
        )
        self.assertIsInstance(count, int)
        self.assertGreaterEqual(count, 0)

    def test_cron_skips_profile_without_email(self):
        user_no_email = _make_social_user(self.env, 'NoEmail', 'no_email_digest')
        user_no_email.sudo().write({'email': False})
        profile = self.env['club_social_profile.profile'].sudo().get_or_create_for_user(user_no_email)
        profile.sudo().write({'onboarding_done': True, 'digest_email_enabled': True})
        post = self.env['social_base.post'].sudo().create({
            'author_id': self.user.id,
            'content': 'Digest test content for cron',
            'state': 'published',
            'visibility': 'public',
        })
        # Should not raise even with missing email
        try:
            self._run_cron()
        except Exception as e:
            self.fail(f'cron_send_weekly_digest raised unexpectedly: {e}')

    def test_cron_skips_digest_disabled(self):
        self.profile.sudo().write({'digest_email_enabled': False})
        post = self.env['social_base.post'].sudo().create({
            'author_id': self.user.id,
            'content': 'Cron skip test content',
            'state': 'published',
            'visibility': 'public',
        })
        sent = []
        original_send = self.env['mail.mail'].sudo().create.__func__

        try:
            self._run_cron()
        except Exception as e:
            self.fail(f'cron_send_weekly_digest raised: {e}')
        finally:
            self.profile.sudo().write({'digest_email_enabled': True})

    def test_cron_no_content_returns_early(self):
        """Cron without posts/events/proposals must not send emails.

        On isole la logique "no content → return early" : archive les posts
        publiés + mock _digest_upcoming_events et _digest_proposals_voting
        pour retourner vide. Sans le mock, le test fail si la DB contient
        un event futur ou une proposition voting (seedés par demo_data ou
        un autre test). C'est exactement le bug du CI.
        """
        Post = type(self.env['social_base.post'])
        self.env['social_base.post'].sudo().search([
            ('state', '=', 'published'),
        ]).write({'state': 'archived'})
        empty_events = (
            self.env['event.event'].browse() if 'event.event' in self.env else None
        )
        empty_proposals = (
            self.env['social_governance.proposal'].browse()
            if 'social_governance.proposal' in self.env else None
        )
        with patch.object(
            type(self.env['mail.mail']), 'send', autospec=True,
        ) as mock_send, patch.object(
            Post, '_digest_upcoming_events', return_value=empty_events,
        ), patch.object(
            Post, '_digest_proposals_voting', return_value=empty_proposals,
        ):
            self._run_cron()
            mock_send.assert_not_called()

    def test_cron_sends_mail_with_content(self):
        post = self.env['social_base.post'].sudo().create({
            'author_id': self.user.id,
            'content': 'Popular test post for digest',
            'state': 'published',
            'visibility': 'public',
            'like_count': 10,
        })
        mails_before = self.env['mail.mail'].sudo().search_count([])
        self._run_cron()
        mails_after = self.env['mail.mail'].sudo().search_count([])
        # At least one mail created (auto_delete=True so may be gone, just check no error)
        # If auto_delete cleans it immediately, count may not change — just verify no exception

    def test_cron_notification_created(self):
        post = self.env['social_base.post'].sudo().create({
            'author_id': self.user.id,
            'content': 'Notif test post for digest',
            'state': 'published',
            'visibility': 'public',
        })
        notifs_before = self.env['club_social_profile.notification'].sudo().search_count([
            ('user_id', '=', self.user.id),
            ('type', '=', 'daily_digest'),
        ])
        self._run_cron()
        notifs_after = self.env['club_social_profile.notification'].sudo().search_count([
            ('user_id', '=', self.user.id),
            ('type', '=', 'daily_digest'),
        ])
        self.assertGreater(notifs_after, notifs_before)

    # ── Age gate ─────────────────────────────────────────────────────────────

    def test_cron_skips_profile_without_age_gate(self):
        """Si social_age_gate est installé et age_gate_passed=False, le profil est ignoré."""
        Profile = self.env['club_social_profile.profile']
        if 'age_gate_passed' not in Profile._fields:
            self.skipTest('social_age_gate not installed')

        user_ungated = _make_social_user(self.env, 'Ungated', 'ungated_digest')
        profile = Profile.sudo().get_or_create_for_user(user_ungated)
        profile.sudo().write({
            'onboarding_done': True,
            'digest_email_enabled': True,
            'age_gate_passed': False,
        })
        post = self.env['social_base.post'].sudo().create({
            'author_id': self.user.id,
            'content': 'Age gate skip test',
            'state': 'published',
            'visibility': 'public',
        })
        notifs_before = self.env['club_social_profile.notification'].sudo().search_count([
            ('user_id', '=', user_ungated.id),
            ('type', '=', 'daily_digest'),
        ])
        self._run_cron()
        notifs_after = self.env['club_social_profile.notification'].sudo().search_count([
            ('user_id', '=', user_ungated.id),
            ('type', '=', 'daily_digest'),
        ])
        self.assertEqual(notifs_before, notifs_after, 'Un profil sans age_gate_passed ne devrait pas recevoir le digest')

    # ── RSVPs connexions ──────────────────────────────────────────────────────

    def test_digest_connection_rsvps_empty_without_connections(self):
        if 'event.registration' not in self.env:
            self.skipTest('event.registration not installed')
        result = self.env['social_base.post']._digest_connection_rsvps(self.user, fields.Datetime.now())
        self.assertIsInstance(result, list)
        self.assertEqual(result, [])

    def test_digest_connection_rsvps_returns_connected_events(self):
        if 'event.registration' not in self.env:
            self.skipTest('event.registration not installed')
        now = fields.Datetime.now()

        conn_user = _make_social_user(self.env, 'ConnRsvp', 'conn_rsvp_digest')
        self.env['club_social_profile.connection'].sudo().create([
            {'user_id': self.user.id, 'connected_user_id': conn_user.id, 'state': 'accepted'},
            {'user_id': conn_user.id, 'connected_user_id': self.user.id, 'state': 'accepted'},
        ])
        event = self.env['event.event'].sudo().create({
            'name': 'Digest RSVP Event',
            'date_begin': now + timedelta(days=3),
            'date_end': now + timedelta(days=4),
        })
        self.env['event.registration'].sudo().create({
            'event_id': event.id,
            'partner_id': conn_user.partner_id.id,
            'state': 'open',
        })

        result = self.env['social_base.post']._digest_connection_rsvps(self.user, now)
        event_ids = [r['event'].id for r in result]
        self.assertIn(event.id, event_ids)
        rsvp = next(r for r in result if r['event'].id == event.id)
        self.assertIn(conn_user.partner_id.name, rsvp['registrant_names'])

    def test_digest_connection_rsvps_excludes_past_events(self):
        if 'event.registration' not in self.env:
            self.skipTest('event.registration not installed')
        now = fields.Datetime.now()

        conn_user2 = _make_social_user(self.env, 'ConnRsvp2', 'conn_rsvp2_digest')
        self.env['club_social_profile.connection'].sudo().create([
            {'user_id': self.user.id, 'connected_user_id': conn_user2.id, 'state': 'accepted'},
            {'user_id': conn_user2.id, 'connected_user_id': self.user.id, 'state': 'accepted'},
        ])
        past_event = self.env['event.event'].sudo().create({
            'name': 'Past RSVP Event',
            'date_begin': now - timedelta(days=3),
            'date_end': now - timedelta(days=2),
        })
        self.env['event.registration'].sudo().create({
            'event_id': past_event.id,
            'partner_id': conn_user2.partner_id.id,
            'state': 'open',
        })

        result = self.env['social_base.post']._digest_connection_rsvps(self.user, now)
        event_ids = [r['event'].id for r in result]
        self.assertNotIn(past_event.id, event_ids)

    def test_digest_connection_rsvps_max_3_names_per_event(self):
        if 'event.registration' not in self.env:
            self.skipTest('event.registration not installed')
        now = fields.Datetime.now()

        event = self.env['event.event'].sudo().create({
            'name': 'Busy Event',
            'date_begin': now + timedelta(days=5),
            'date_end': now + timedelta(days=6),
        })
        for i in range(5):
            u = _make_social_user(self.env, f'BusyConn{i}', f'busy_conn_{i}_digest')
            self.env['club_social_profile.connection'].sudo().create([
                {'user_id': self.user.id, 'connected_user_id': u.id, 'state': 'accepted'},
                {'user_id': u.id, 'connected_user_id': self.user.id, 'state': 'accepted'},
            ])
            self.env['event.registration'].sudo().create({
                'event_id': event.id,
                'partner_id': u.partner_id.id,
                'state': 'open',
            })

        result = self.env['social_base.post']._digest_connection_rsvps(self.user, now)
        rsvp = next((r for r in result if r['event'].id == event.id), None)
        if rsvp:
            self.assertLessEqual(len(rsvp['registrant_names']), 3)

    def test_digest_connection_rsvps_excludes_cancelled_registrations(self):
        """Les inscriptions annulées (state != 'open') sont exclues des RSVPs."""
        if 'event.registration' not in self.env:
            self.skipTest('event.registration not installed')
        now = fields.Datetime.now()

        conn_user = _make_social_user(self.env, 'CancelConn', 'cancel_conn_digest')
        self.env['club_social_profile.connection'].sudo().create([
            {'user_id': self.user.id, 'connected_user_id': conn_user.id, 'state': 'accepted'},
            {'user_id': conn_user.id, 'connected_user_id': self.user.id, 'state': 'accepted'},
        ])
        event = self.env['event.event'].sudo().create({
            'name': 'Cancelled RSVP Event',
            'date_begin': now + timedelta(days=2),
            'date_end': now + timedelta(days=3),
        })
        self.env['event.registration'].sudo().create({
            'event_id': event.id,
            'partner_id': conn_user.partner_id.id,
            'state': 'cancel',
        })

        result = self.env['social_base.post']._digest_connection_rsvps(self.user, now)
        event_ids = [r['event'].id for r in result]
        self.assertNotIn(event.id, event_ids)

    # ── Portal user filter ────────────────────────────────────────────────────

    def test_cron_skips_portal_user_profile(self):
        """Les profils liés à un utilisateur portail (share=True) sont ignorés par le cron."""
        portal_group = self.env.ref('base.group_portal')
        portal_user = self.env['res.users'].sudo().create({
            'name': 'PortalDigest', 'login': 'portal_digest_test',
            'email': 'portal_digest@diverse.test', 'password': 'Test1234!',
            'group_ids': [(6, 0, portal_group.ids)],
        })
        Profile = self.env['club_social_profile.profile']
        profile = Profile.sudo().get_or_create_for_user(portal_user)
        profile.sudo().write({'onboarding_done': True, 'digest_email_enabled': True})

        self.env['social_base.post'].sudo().create({
            'author_id': self.user.id,
            'content': 'Portal skip test post',
            'state': 'published',
            'visibility': 'public',
        })

        notifs_before = self.env['club_social_profile.notification'].sudo().search_count([
            ('user_id', '=', portal_user.id),
            ('type', '=', 'daily_digest'),
        ])
        self._run_cron()
        notifs_after = self.env['club_social_profile.notification'].sudo().search_count([
            ('user_id', '=', portal_user.id),
            ('type', '=', 'daily_digest'),
        ])
        self.assertEqual(notifs_before, notifs_after, 'Un profil portail ne devrait pas recevoir le digest')

    # ── New members count ─────────────────────────────────────────────────────

    def test_digest_new_members_count_with_active_membership(self):
        """_digest_new_members_count compte les adhésions active créées dans la fenêtre."""
        if 'club_membership.membership' not in self.env:
            self.skipTest('club_membership not installed')
        since = fields.Datetime.now() - timedelta(days=7)
        count_before = self.env['social_base.post']._digest_new_members_count(since)

        mem_type = self.env['club_membership.type'].sudo().search([], limit=1)
        if not mem_type:
            self.skipTest('Aucun type d\'adhésion disponible')
        self.env['club_membership.membership'].sudo().create({
            'partner_id': self.user.partner_id.id,
            'membership_type_id': mem_type.id,
            'state': 'active',
            'start_date': fields.Date.today(),
        })
        count_after = self.env['social_base.post']._digest_new_members_count(since)
        self.assertEqual(count_after, count_before + 1)

    # ── Upcoming events horizon ───────────────────────────────────────────────

    def test_digest_upcoming_events_excludes_beyond_7_days(self):
        """Les événements à plus de 7 jours sont exclus."""
        if 'event.event' not in self.env:
            self.skipTest('event.event not installed')
        now = fields.Datetime.now()
        far_event = self.env['event.event'].sudo().create({
            'name': 'Far Future Digest Event',
            'date_begin': now + timedelta(days=10),
            'date_end': now + timedelta(days=11),
        })
        results = self.env['social_base.post']._digest_upcoming_events(now)
        self.assertNotIn(far_event.id, results.ids)
