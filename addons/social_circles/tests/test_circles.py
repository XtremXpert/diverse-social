from odoo.tests import TransactionCase, tagged
from odoo.exceptions import ValidationError


@tagged('social_circles', 'circles')
class TestSocialCircles(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        group_user = cls.env.ref('social_base.group_social_user')
        cls.owner = cls.env['res.users'].create({
            'name': 'Circle Owner', 'login': 'circles_owner', 'email': 'owner@circles.test',
            'group_ids': [(4, group_user.id)],
        })
        cls.friend = cls.env['res.users'].create({
            'name': 'Friend', 'login': 'circles_friend', 'email': 'friend@circles.test',
            'group_ids': [(4, group_user.id)],
        })
        cls.acquaintance = cls.env['res.users'].create({
            'name': 'Acquaintance', 'login': 'circles_acquaintance', 'email': 'acq@circles.test',
            'group_ids': [(4, group_user.id)],
        })
        cls.stranger = cls.env['res.users'].create({
            'name': 'Stranger', 'login': 'circles_stranger', 'email': 'stranger@circles.test',
            'group_ids': [(4, group_user.id)],
        })
        cls.Profile = cls.env['club_social_profile.profile']
        cls.owner_profile = cls.Profile.get_or_create_for_user(cls.owner)
        # Circle types used across tests — created here to avoid depending on demo data
        CircleType = cls.env['social_circles.circle_type']
        cls.type_close = CircleType.create({'name': 'Close Friends T', 'sequence': 10})
        cls.type_play = CircleType.create({'name': 'Play Partners T', 'sequence': 20})
        cls.type_trusted = CircleType.create({'name': 'Trusted T', 'sequence': 30})
        cls.type_vip = CircleType.create({'name': 'VIP T', 'sequence': 5})
        cls.type_inner = CircleType.create({'name': 'Inner T', 'sequence': 40})
        cls.type_outer = CircleType.create({'name': 'Outer T', 'sequence': 50})
        cls.type_besties = CircleType.create({'name': 'Besties T', 'sequence': 15})
        cls.type_count = CircleType.create({'name': 'Count Test T', 'sequence': 60})
        cls.type_seq = CircleType.create({'name': 'Seq Circle T', 'sequence': 70})
        cls.type_stable = CircleType.create({'name': 'Stable T', 'sequence': 80})
        cls.type_shared = CircleType.create({'name': 'Shared Name T', 'sequence': 90})
        cls.type_foreign = CircleType.create({'name': 'Foreign T', 'sequence': 95})
        cls.type_proches = CircleType.create({'name': 'Proches Test T', 'sequence': 25})
        cls.type_generic = CircleType.create({'name': 'Generic T', 'sequence': 100, 'is_default': False})

    def _make_circle(self, type_id, members=None, sequence=10, nickname=None):
        """Helper: create a circle for owner_profile with the given type."""
        vals = {
            'profile_id': self.owner_profile.id,
            'type_id': type_id.id,
            'sequence': sequence,
        }
        if nickname:
            vals['name'] = nickname
        circle = self.env['social_circles.circle'].sudo().create(vals)
        if members:
            circle.write({'member_ids': [(4, u.id) for u in members]})
        return circle

    # ── Circle CRUD ───────────────────────────────────────────────────────────

    def test_create_circle(self):
        circle = self._make_circle(self.type_close, members=[self.friend])
        self.assertEqual(circle.profile_id, self.owner_profile)
        self.assertIn(self.friend, circle.member_ids)
        self.assertEqual(circle.member_count, 1)

    def test_duplicate_name_raises(self):
        """Two circles of the same type on the same profile raises ValidationError."""
        self._make_circle(self.type_play)
        with self.assertRaises(ValidationError):
            self._make_circle(self.type_play)

    def test_add_remove_member(self):
        circle = self._make_circle(self.type_trusted)
        circle.add_member(self.friend)
        self.assertTrue(circle.has_member(self.friend))
        circle.remove_member(self.friend)
        self.assertFalse(circle.has_member(self.friend))

    def test_ensure_circle_creates_once(self):
        c1 = self.owner_profile.ensure_circle(self.type_vip)
        c2 = self.owner_profile.ensure_circle(self.type_vip)
        self.assertEqual(c1, c2)

    # ── Profile visibility methods ────────────────────────────────────────────

    def test_get_circles_for_member(self):
        circle = self._make_circle(self.type_inner, members=[self.friend])
        circles = self.owner_profile.get_circles_for(self.friend)
        self.assertIn(circle, circles)

    def test_get_circles_for_non_member(self):
        self._make_circle(self.type_inner, members=[self.friend])
        circles = self.owner_profile.get_circles_for(self.stranger)
        self.assertFalse(circles)

    def test_is_in_any_circle(self):
        self._make_circle(self.type_inner, members=[self.friend])
        self.assertTrue(self.owner_profile.is_in_any_circle(self.friend))
        self.assertFalse(self.owner_profile.is_in_any_circle(self.stranger))

    # ── can_see_detailed_info ─────────────────────────────────────────────────

    def test_visibility_members(self):
        self.owner_profile.detailed_visibility = 'members'
        self.assertTrue(self.owner_profile.can_see_detailed_info(self.stranger))

    def test_visibility_private(self):
        self.owner_profile.detailed_visibility = 'private'
        self.assertFalse(self.owner_profile.can_see_detailed_info(self.stranger))
        self.assertTrue(self.owner_profile.can_see_detailed_info(self.owner))

    def test_visibility_circles_only(self):
        self.owner_profile.detailed_visibility = 'circles'
        circle = self._make_circle(self.type_vip, members=[self.friend])
        self.assertTrue(self.owner_profile.can_see_detailed_info(self.friend))
        self.assertFalse(self.owner_profile.can_see_detailed_info(self.acquaintance))

    def test_visibility_specific_circle(self):
        circle = self._make_circle(self.type_inner, members=[self.friend])
        other_circle = self._make_circle(self.type_outer, members=[self.acquaintance])
        self.owner_profile.write({
            'detailed_visibility': 'specific',
            'detailed_visibility_circle_id': circle.id,
        })
        self.assertTrue(self.owner_profile.can_see_detailed_info(self.friend))
        self.assertFalse(self.owner_profile.can_see_detailed_info(self.acquaintance))

    def test_specific_visibility_requires_circle(self):
        with self.assertRaises(ValidationError):
            self.owner_profile.write({
                'detailed_visibility': 'specific',
                'detailed_visibility_circle_id': False,
            })

    def test_visibility_connections(self):
        self.owner_profile.detailed_visibility = 'connections'
        # No connection exists — should be False
        self.assertFalse(self.owner_profile.can_see_detailed_info(self.friend))
        # Simulate a connection
        self.env['club_social_profile.connection'].sudo().create({
            'user_id': self.owner.id,
            'connected_user_id': self.friend.id,
            'state': 'accepted',
        })
        self.assertTrue(self.owner_profile.can_see_detailed_info(self.friend))

    # ── get_visibility_level_for ──────────────────────────────────────────────

    def test_level_owner(self):
        self.assertEqual(self.owner_profile.get_visibility_level_for(self.owner), 'owner')

    def test_level_circle(self):
        self._make_circle(self.type_besties, members=[self.friend])
        level = self.owner_profile.get_visibility_level_for(self.friend)
        self.assertTrue(level.startswith('circle:'))

    def test_level_member(self):
        level = self.owner_profile.get_visibility_level_for(self.stranger)
        self.assertEqual(level, 'member')

    def test_level_connection(self):
        """Un utilisateur connecté mais non dans un cercle obtient le niveau 'connection'."""
        self.env['club_social_profile.connection'].sudo().create({
            'user_id': self.owner.id,
            'connected_user_id': self.acquaintance.id,
            'state': 'accepted',
        })
        level = self.owner_profile.get_visibility_level_for(self.acquaintance)
        self.assertEqual(level, 'connection')

    def test_level_anonymous(self):
        """Un utilisateur sans groupe social obtient le niveau 'anonymous'."""
        non_social = self.env['res.users'].create({
            'name': 'Non Social', 'login': 'circ_nonsocial', 'email': 'ns@circles.test',
        })
        level = self.owner_profile.get_visibility_level_for(non_social)
        self.assertEqual(level, 'anonymous')

    def test_level_circle_contains_name(self):
        """Le niveau circle: contient le display_name du cercle."""
        self._make_circle(self.type_proches, members=[self.friend])
        level = self.owner_profile.get_visibility_level_for(self.friend)
        self.assertIn(self.type_proches.name, level)

    # ── circle_count et ensure_circle ─────────────────────────────────────────

    def test_circle_count_updates(self):
        """circle_count est incrémenté à la création d'un cercle."""
        before = self.owner_profile.circle_count
        self._make_circle(self.type_count)
        self.owner_profile.invalidate_recordset(['circle_count'])
        self.assertGreater(self.owner_profile.circle_count, before)

    def test_ensure_circle_custom_sequence(self):
        """ensure_circle uses the type's sequence."""
        circle = self.owner_profile.ensure_circle(self.type_seq)
        self.assertEqual(circle.sequence, self.type_seq.sequence)

    def test_ensure_circle_existing_not_overwritten(self):
        """ensure_circle returns the existing circle without modifying it."""
        c1 = self.owner_profile.ensure_circle(self.type_stable)
        c2 = self.owner_profile.ensure_circle(self.type_stable)
        self.assertEqual(c1, c2)

    def test_duplicate_type_different_profiles_allowed(self):
        """Two different profiles can each have a circle of the same type."""
        other_user = self.env['res.users'].create({
            'name': 'Other Owner', 'login': 'circ_other_owner', 'email': 'other@circles.test',
            'group_ids': [(4, self.env.ref('social_base.group_social_user').id)],
        })
        other_profile = self.Profile.get_or_create_for_user(other_user)
        self._make_circle(self.type_shared)
        other_circle = self.env['social_circles.circle'].sudo().create({
            'profile_id': other_profile.id,
            'type_id': self.type_shared.id,
        })
        self.assertTrue(other_circle.exists())

    def test_owner_always_sees_own_profile(self):
        """Le propriétaire voit toujours son profil même en visibilité 'private'."""
        self.owner_profile.sudo().write({'detailed_visibility': 'private'})
        self.assertTrue(self.owner_profile.can_see_detailed_info(self.owner))
        self.owner_profile.sudo().write({'detailed_visibility': 'members'})

    def test_specific_circle_wrong_profile_raises(self):
        """Attribuer un cercle d'un autre profil à detailed_visibility_circle_id lève ValidationError."""
        other_user = self.env['res.users'].create({
            'name': 'Wrong Owner', 'login': 'circ_wrong_owner2', 'email': 'wo2@circles.test',
            'group_ids': [(4, self.env.ref('social_base.group_social_user').id)],
        })
        other_profile = self.Profile.get_or_create_for_user(other_user)
        foreign_circle = self.env['social_circles.circle'].sudo().create({
            'profile_id': other_profile.id,
            'type_id': self.type_foreign.id,
        })
        with self.assertRaises(ValidationError):
            self.owner_profile.write({
                'detailed_visibility': 'specific',
                'detailed_visibility_circle_id': foreign_circle.id,
            })
