from odoo.tests import TransactionCase, tagged
from odoo.exceptions import UserError, ValidationError
import datetime


@tagged('social_events', 'social_event')
class TestSocialEvents(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        group_user = cls.env.ref('base.group_user')
        group_social = cls.env.ref('social_base.group_social_user')
        group_mod = cls.env.ref('social_base.group_social_moderator')
        # Ensure event access is available regardless of implied-group propagation timing
        group_event_desk = cls.env.ref('event.group_event_registration_desk')
        group_event_user = cls.env.ref('event.group_event_user')

        def make_user(name, login, extra_groups=None):
            groups = [(4, group_user.id), (4, group_social.id), (4, group_event_desk.id)]
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

        # Shared circle type required by social_circles.circle
        cls.circle_type = cls.env['social_circles.circle_type'].create({
            'name': 'Test Type',
        })

        # Alice's circle containing Bob (not Carol)
        cls.inner_circle = cls.env['social_circles.circle'].create({
            'profile_id': cls.alice_profile.id,
            'name': 'Inner Circle',
            'type_id': cls.circle_type.id,
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

    # ── Cas limites _check_social_access ─────────────────────────────────────

    def test_no_visibility_always_accessible(self):
        """Un événement sans social_visibility est accessible à tous."""
        event = self._make_event(visibility='members')
        event.sudo().write({'social_visibility': False})
        self.assertTrue(event._check_social_access(self.carol))

    def test_members_inaccessible_to_non_social_user(self):
        """Un utilisateur sans group_social_user n'accède pas à un événement 'members'."""
        non_social = self.env['res.users'].create({
            'name': 'Non Social', 'login': 'sevt_nonsocial', 'email': 'nonsocial@evt.test',
        })
        event = self._make_event(visibility='members')
        self.assertFalse(event._check_social_access(non_social))

    def test_circles_access_uses_env_user_when_no_arg(self):
        """Sans argument, _check_social_access utilise self.env.user."""
        event = self._make_event(visibility='circles', circles=self.inner_circle)
        # Bob est dans le cercle : son env doit retourner True
        self.assertTrue(event.with_user(self.bob)._check_social_access())

    def test_circles_env_user_outsider_returns_false(self):
        event = self._make_event(visibility='circles', circles=self.inner_circle)
        self.assertFalse(event.with_user(self.carol)._check_social_access())

    def test_multiple_circles_access_any_match(self):
        """Accès accordé si l'utilisateur est dans au moins un des cercles autorisés."""
        Profile = self.env['club_social_profile.profile']
        alice_profile2 = Profile.get_or_create_for_user(self.alice)
        second_type = self.env['social_circles.circle_type'].create({'name': 'Second Type'})
        second_circle = self.env['social_circles.circle'].create({
            'profile_id': alice_profile2.id,
            'name': 'Second Circle',
            'type_id': second_type.id,
        })
        second_circle.add_member(self.carol)
        event = self._make_event(
            visibility='circles',
            circles=self.inner_circle | second_circle,
        )
        # Bob est dans inner_circle, Carol dans second_circle
        self.assertTrue(event._check_social_access(self.bob))
        self.assertTrue(event._check_social_access(self.carol))

    def test_update_circles_after_creation(self):
        """Modifier les cercles autorisés change l'accès."""
        event = self._make_event(visibility='circles', circles=self.inner_circle)
        self.assertFalse(event._check_social_access(self.carol))
        # Ajouter un cercle contenant Carol
        Profile = self.env['club_social_profile.profile']
        carol_profile = Profile.get_or_create_for_user(self.alice)
        new_type = self.env['social_circles.circle_type'].create({'name': 'Carol Type'})
        new_circle = self.env['social_circles.circle'].create({
            'profile_id': carol_profile.id,
            'name': 'Carol Circle',
            'type_id': new_type.id,
        })
        new_circle.add_member(self.carol)
        event.sudo().write({'allowed_circle_ids': [(4, new_circle.id)]})
        self.assertTrue(event._check_social_access(self.carol))

    def test_remove_all_circles_raises_constraint(self):
        """Retirer tous les cercles d'un événement 'circles' lève une UserError."""
        event = self._make_event(visibility='circles', circles=self.inner_circle)
        with self.assertRaises(UserError):
            event.sudo().write({'allowed_circle_ids': [(5,)]})

    def test_allowed_circle_ids_stored(self):
        """Les cercles autorisés sont bien persistés."""
        event = self._make_event(visibility='circles', circles=self.inner_circle)
        self.assertIn(self.inner_circle, event.allowed_circle_ids)

    def test_members_event_invisible_to_non_social_in_search(self):
        """Un utilisateur portail (sans groupe social) ne trouve pas l'événement 'members'."""
        from odoo.exceptions import AccessError
        # Portail: website_event limite la lecture aux événements publiés → l'événement de test
        # n'étant pas publié, il est invisible pour les non-membres sociaux.
        non_social = self.env['res.users'].create({
            'name': 'Non Social Search', 'login': 'sevt_nss', 'email': 'nss@evt.test',
            'group_ids': [(4, self.env.ref('base.group_portal').id)],
        })
        event = self._make_event(visibility='members')
        try:
            found = self.Event.with_user(non_social).search([('id', '=', event.id)])
            self.assertFalse(found)
        except AccessError:
            pass  # No access to events at all → event is not visible
