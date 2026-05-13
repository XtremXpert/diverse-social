from odoo.tests import TransactionCase, tagged
from odoo.exceptions import UserError, ValidationError
import datetime


@tagged('social_events', 'social_event')
class TestSocialEvents(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        group_user = cls.env.ref('social_base.group_social_user')
        group_mod = cls.env.ref('social_base.group_social_moderator')
        # Ensure event access is available regardless of implied-group propagation timing
        group_event_desk = cls.env.ref('event.group_event_registration_desk')
        group_event_user = cls.env.ref('event.group_event_user')

        def make_user(name, login, extra_groups=None):
            groups = [(4, group_user.id), (4, group_event_desk.id)]
            for g in (extra_groups or []):
                groups.append((4, g.id))
            return cls.env['res.users'].create({
                'name': name, 'login': login, 'email': f'{login}@evt.test',
                'group_ids': groups,
            })

        cls.alice = make_user('Alice', 'sevt_alice', extra_groups=[group_mod, group_event_user])
        cls.bob = make_user('Bob', 'sevt_bob')
        cls.carol = make_user('Carol', 'sevt_carol')

        # Profiles for circles
        Profile = cls.env['club_social_profile.profile']
        cls.alice_profile = Profile.get_or_create_for_user(cls.alice)

        # Alice's circle containing Bob (not Carol)
        cls.inner_circle = cls.env['social_circles.circle'].create({
            'profile_id': cls.alice_profile.id,
            'name': 'Inner Circle',
        })
        cls.inner_circle.add_member(cls.bob)

        cls.Event = cls.env['event.event']
        cls.Reg = cls.env['event.registration']

        # Minimal stage required by event.event
        cls.stage = cls.env['event.stage'].search([], limit=1)
        if not cls.stage:
            cls.stage = cls.env['event.stage'].create({'name': 'New', 'sequence': 1})

    def _make_event(self, user=None, visibility='members', circles=None):
        user = user or self.alice
        now = datetime.datetime.now()
        vals = {
            'name': 'Test Event',
            'date_begin': now,
            'date_end': now + datetime.timedelta(hours=3),
            'organizer_user_id': user.id,
            'social_visibility': visibility,
        }
        if circles:
            vals['allowed_circle_ids'] = [(6, 0, circles.ids)]
        event = self.Event.with_user(user).create(vals)
        return event

    # ── Visibility field ──────────────────────────────────────────────────────

    def test_default_visibility_members(self):
        event = self._make_event()
        self.assertEqual(event.social_visibility, 'members')

    def test_circles_visibility_requires_circles(self):
        with self.assertRaises(UserError):
            self._make_event(visibility='circles')

    def test_circles_visibility_with_circles(self):
        event = self._make_event(visibility='circles', circles=self.inner_circle)
        self.assertEqual(event.social_visibility, 'circles')

    # ── _check_social_access ─────────────────────────────────────────────────

    def test_members_visible_to_all_social_users(self):
        event = self._make_event(visibility='members')
        self.assertTrue(event._check_social_access(self.alice))
        self.assertTrue(event._check_social_access(self.bob))
        self.assertTrue(event._check_social_access(self.carol))

    def test_circles_visible_to_circle_members(self):
        event = self._make_event(visibility='circles', circles=self.inner_circle)
        self.assertTrue(event._check_social_access(self.bob))

    def test_circles_not_visible_to_outsiders(self):
        event = self._make_event(visibility='circles', circles=self.inner_circle)
        self.assertFalse(event._check_social_access(self.carol))

    def test_organizer_in_allowed_circle_can_access(self):
        # Alice is the organizer — add her to her own circle
        self.inner_circle.add_member(self.alice)
        event = self._make_event(visibility='circles', circles=self.inner_circle)
        self.assertTrue(event._check_social_access(self.alice))
        self.inner_circle.remove_member(self.alice)

    # ── Registration access control ───────────────────────────────────────────

    def test_member_can_register_members_event(self):
        event = self._make_event(visibility='members')
        reg = self.Reg.with_user(self.carol).create({
            'event_id': event.id,
            'partner_id': self.carol.partner_id.id,
        })
        self.assertEqual(reg.event_id, event)

    def test_circle_member_can_register(self):
        event = self._make_event(visibility='circles', circles=self.inner_circle)
        reg = self.Reg.with_user(self.bob).create({
            'event_id': event.id,
            'partner_id': self.bob.partner_id.id,
        })
        self.assertEqual(reg.event_id, event)

    def test_outsider_cannot_register_circle_event(self):
        event = self._make_event(visibility='circles', circles=self.inner_circle)
        with self.assertRaises(UserError):
            self.Reg.with_user(self.carol).create({
                'event_id': event.id,
                'partner_id': self.carol.partner_id.id,
            })

    # ── Record rule: search visibility ───────────────────────────────────────

    def test_members_event_visible_in_search(self):
        event = self._make_event(visibility='members')
        found = self.Event.with_user(self.carol).search([('id', '=', event.id)])
        self.assertTrue(found)

    def test_circle_event_visible_to_member(self):
        event = self._make_event(visibility='circles', circles=self.inner_circle)
        found = self.Event.with_user(self.bob).search([('id', '=', event.id)])
        self.assertTrue(found)

    def test_circle_event_hidden_from_outsider(self):
        event = self._make_event(visibility='circles', circles=self.inner_circle)
        found = self.Event.with_user(self.carol).search([('id', '=', event.id)])
        self.assertFalse(found)

    # ── Organizer field ───────────────────────────────────────────────────────

    def test_organizer_user_default(self):
        event = self._make_event(user=self.alice)
        self.assertEqual(event.organizer_user_id, self.alice)

    # ── Registration workflow (native Odoo) ───────────────────────────────────

    def test_registration_confirm(self):
        event = self._make_event(visibility='members')
        reg = self.Reg.with_user(self.bob).create({
            'event_id': event.id,
            'partner_id': self.bob.partner_id.id,
        })
        reg.action_confirm()
        self.assertEqual(reg.state, 'open')

    def test_registration_done(self):
        event = self._make_event(visibility='members')
        reg = self.Reg.with_user(self.bob).create({
            'event_id': event.id,
            'partner_id': self.bob.partner_id.id,
        })
        reg.action_confirm()
        reg.action_set_done()
        self.assertEqual(reg.state, 'done')

    def test_registration_cancel(self):
        event = self._make_event(visibility='members')
        reg = self.Reg.with_user(self.bob).create({
            'event_id': event.id,
            'partner_id': self.bob.partner_id.id,
        })
        reg.action_cancel()
        self.assertEqual(reg.state, 'cancel')
