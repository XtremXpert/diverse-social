import datetime

from odoo import fields
from odoo.tests import TransactionCase, tagged


@tagged('social_notifications', 'notifications')
class TestSocialNotifications(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        group_social = cls.env.ref('social_base.group_social_user')
        group_mod = cls.env.ref('social_base.group_social_moderator')
        group_event_desk = cls.env.ref('event.group_event_registration_desk')
        group_event_user = cls.env.ref('event.group_event_user')
        cls.proposal_category = cls.env.ref('social_governance.category_other')

        def make_user(name, login, extra_groups=None):
            groups = [(4, group_social.id), (4, group_event_desk.id)]
            for g in (extra_groups or []):
                groups.append((4, g.id))
            return cls.env['res.users'].create({
                'name': name, 'login': login, 'email': f'{login}@notif.test',
                'group_ids': groups,
            })

        cls.alice = make_user('Alice', 'notif_alice', extra_groups=[group_mod, group_event_user])
        cls.bob = make_user('Bob', 'notif_bob')
        cls.carol = make_user('Carol', 'notif_carol')

        cls.Notif = cls.env['club_social_profile.notification']

    def _notifs_for(self, user, notif_type=None):
        domain = [('user_id', '=', user.id)]
        if notif_type:
            domain.append(('type', '=', notif_type))
        return self.Notif.search(domain)

    # ── Bus push on create ────────────────────────────────────────────────────

    def test_notification_create_triggers_bus(self):
        # Just verify that create does not raise (bus mock in tests)
        notif = self.Notif.sudo().create({
            'user_id': self.bob.id,
            'actor_id': self.alice.id,
            'type': 'connection_request',
            'body': 'Test bus push',
        })
        self.assertTrue(notif.exists())

    # ── Event registration ────────────────────────────────────────────────────

    def test_event_registration_notifies_organizer(self):
        stage = self.env['event.stage'].search([], limit=1)
        if not stage:
            stage = self.env['event.stage'].create({'name': 'New', 'sequence': 1})
        now = datetime.datetime.now()
        event = self.env['event.event'].with_user(self.alice).create({
            'name': 'Test Event',
            'date_begin': now,
            'date_end': now + datetime.timedelta(hours=2),
            'organizer_user_id': self.alice.id,
            'social_visibility': 'members',
        })
        before = len(self._notifs_for(self.alice, 'event_registration'))
        self.env['event.registration'].with_user(self.bob).create({
            'event_id': event.id,
            'partner_id': self.bob.partner_id.id,
        })
        after = len(self._notifs_for(self.alice, 'event_registration'))
        self.assertEqual(after, before + 1)

    def test_organizer_not_notified_for_own_registration(self):
        stage = self.env['event.stage'].search([], limit=1)
        now = datetime.datetime.now()
        event = self.env['event.event'].with_user(self.alice).create({
            'name': 'Self Event',
            'date_begin': now,
            'date_end': now + datetime.timedelta(hours=2),
            'organizer_user_id': self.alice.id,
            'social_visibility': 'members',
        })
        before = len(self._notifs_for(self.alice, 'event_registration'))
        self.env['event.registration'].with_user(self.alice).create({
            'event_id': event.id,
            'partner_id': self.alice.partner_id.id,
        })
        after = len(self._notifs_for(self.alice, 'event_registration'))
        self.assertEqual(after, before)

    # ── Governance: proposal_voting ───────────────────────────────────────────

    def test_proposal_voting_notifies_all_social_users(self):
        proposal = self.env['social_governance.proposal'].with_user(self.alice).create({
            'name': 'Test Proposal',
            'description': '<p>Details</p>',
            'author_id': self.alice.id,
            'category_id': self.proposal_category.id,
            'voting_closes_at': fields.Datetime.now() + datetime.timedelta(days=7),
        })
        before_bob = len(self._notifs_for(self.bob, 'proposal_voting'))
        before_carol = len(self._notifs_for(self.carol, 'proposal_voting'))
        proposal.action_start_voting()
        self.assertEqual(len(self._notifs_for(self.bob, 'proposal_voting')), before_bob + 1)
        self.assertEqual(len(self._notifs_for(self.carol, 'proposal_voting')), before_carol + 1)

    def test_proposal_author_not_notified(self):
        proposal = self.env['social_governance.proposal'].with_user(self.alice).create({
            'name': 'Another Proposal',
            'description': '<p>Details</p>',
            'author_id': self.alice.id,
            'category_id': self.proposal_category.id,
            'voting_closes_at': fields.Datetime.now() + datetime.timedelta(days=7),
        })
        before = len(self._notifs_for(self.alice, 'proposal_voting'))
        proposal.action_start_voting()
        self.assertEqual(len(self._notifs_for(self.alice, 'proposal_voting')), before)

    # ── Group join request ────────────────────────────────────────────────────

    def test_group_join_request_notifies_admin(self):
        group = self.env['social_group.group'].with_user(self.alice).create({
            'name': 'Test Group',
            'creator_id': self.alice.id,
            'admin_ids': [(4, self.alice.id)],
            'privacy': 'private',
            'join_type': 'approval',
        })
        before = len(self._notifs_for(self.alice, 'group_join_request'))
        self.env['social_group.join_request'].with_user(self.bob).create({
            'group_id': group.id,
            'user_id': self.bob.id,
        })
        self.assertEqual(len(self._notifs_for(self.alice, 'group_join_request')), before + 1)

    def test_group_join_approved_notifies_requester(self):
        group = self.env['social_group.group'].with_user(self.alice).create({
            'name': 'Approval Group',
            'creator_id': self.alice.id,
            'admin_ids': [(4, self.alice.id)],
            'privacy': 'private',
            'join_type': 'approval',
        })
        req = self.env['social_group.join_request'].sudo().create({
            'group_id': group.id,
            'user_id': self.bob.id,
        })
        before = len(self._notifs_for(self.bob, 'group_join_approved'))
        req.with_user(self.alice).action_approve()
        self.assertEqual(len(self._notifs_for(self.bob, 'group_join_approved')), before + 1)

    # ── Messaging ─────────────────────────────────────────────────────────────

    def test_message_notifies_recipient(self):
        thread = self.env['social_messaging.thread'].sudo()._get_or_create(
            [self.alice.id, self.bob.id]
        )
        before = len(self._notifs_for(self.bob, 'new_message'))
        self.env['social_messaging.message'].sudo().create({
            'thread_id': thread.id,
            'author_id': self.alice.id,
            'content': 'Salut Bob',
        })
        self.assertEqual(len(self._notifs_for(self.bob, 'new_message')), before + 1)

    def test_message_author_not_notified(self):
        thread = self.env['social_messaging.thread'].sudo()._get_or_create(
            [self.alice.id, self.bob.id]
        )
        before = len(self._notifs_for(self.alice, 'new_message'))
        self.env['social_messaging.message'].sudo().create({
            'thread_id': thread.id,
            'author_id': self.alice.id,
            'content': 'Mon propre message',
        })
        self.assertEqual(len(self._notifs_for(self.alice, 'new_message')), before)

    # ── Story hooks ───────────────────────────────────────────────────────────

    def test_story_notifies_connections(self):
        self.env['club_social_profile.connection'].sudo().create({
            'user_id': self.alice.id,
            'connected_user_id': self.bob.id,
            'connection_type': 'friend',
            'state': 'accepted',
        })
        before = len(self._notifs_for(self.bob, 'story_new'))
        self.env['social_story.story'].sudo().create({
            'author_id': self.alice.id,
            'name': 'Ma story',
        })
        self.assertEqual(len(self._notifs_for(self.bob, 'story_new')), before + 1)

    def test_story_does_not_notify_non_connections(self):
        before = len(self._notifs_for(self.carol, 'story_new'))
        self.env['social_story.story'].sudo().create({
            'author_id': self.alice.id,
            'name': 'Private story',
        })
        self.assertEqual(len(self._notifs_for(self.carol, 'story_new')), before)

    # ── Mark read ─────────────────────────────────────────────────────────────

    def test_mark_notification_read(self):
        notif = self.Notif.sudo().create({
            'user_id': self.bob.id,
            'actor_id': self.alice.id,
            'type': 'connection_request',
            'body': 'Test',
        })
        self.assertFalse(notif.is_read)
        notif.action_mark_read()
        self.assertTrue(notif.is_read)
        self.assertTrue(notif.read_at)

    def test_mark_all_read(self):
        self.Notif.sudo().create([
            {'user_id': self.bob.id, 'actor_id': self.alice.id,
             'type': 'connection_request', 'body': 'A'},
            {'user_id': self.bob.id, 'actor_id': self.alice.id,
             'type': 'connection_accepted', 'body': 'B'},
        ])
        count = self.Notif.sudo().mark_all_read(self.bob.id)
        self.assertGreater(count, 0)
        unread = self.Notif.search([('user_id', '=', self.bob.id), ('is_read', '=', False)])
        self.assertFalse(unread)
