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

    def _make_circle(self, name, members=None, sequence=10):
        circle = self.env['social_circles.circle'].sudo().create({
            'profile_id': self.owner_profile.id,
            'name': name,
            'sequence': sequence,
        })
        if members:
            circle.write({'member_ids': [(4, u.id) for u in members]})
        return circle

    # ── Circle CRUD ───────────────────────────────────────────────────────────

    def test_create_circle(self):
        circle = self._make_circle('Close Friends', members=[self.friend])
        self.assertEqual(circle.profile_id, self.owner_profile)
        self.assertIn(self.friend, circle.member_ids)
        self.assertEqual(circle.member_count, 1)

    def test_duplicate_name_raises(self):
        self._make_circle('Play Partners')
        with self.assertRaises(ValidationError):
            self._make_circle('Play Partners')

    def test_add_remove_member(self):
        circle = self._make_circle('Trusted')
        circle.add_member(self.friend)
        self.assertTrue(circle.has_member(self.friend))
        circle.remove_member(self.friend)
        self.assertFalse(circle.has_member(self.friend))

    def test_ensure_circle_creates_once(self):
        c1 = self.owner_profile.ensure_circle('VIP')
        c2 = self.owner_profile.ensure_circle('VIP')
        self.assertEqual(c1, c2)

    # ── Profile visibility methods ────────────────────────────────────────────

    def test_get_circles_for_member(self):
        circle = self._make_circle('Inner', members=[self.friend])
        circles = self.owner_profile.get_circles_for(self.friend)
        self.assertIn(circle, circles)

    def test_get_circles_for_non_member(self):
        self._make_circle('Inner', members=[self.friend])
        circles = self.owner_profile.get_circles_for(self.stranger)
        self.assertFalse(circles)

    def test_is_in_any_circle(self):
        self._make_circle('Inner', members=[self.friend])
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
        circle = self._make_circle('VIP Circle', members=[self.friend])
        self.assertTrue(self.owner_profile.can_see_detailed_info(self.friend))
        self.assertFalse(self.owner_profile.can_see_detailed_info(self.acquaintance))

    def test_visibility_specific_circle(self):
        circle = self._make_circle('Inner Circle', members=[self.friend])
        other_circle = self._make_circle('Outer Circle', members=[self.acquaintance])
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
        self._make_circle('Besties', members=[self.friend])
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
        """Le niveau circle: contient le nom du cercle."""
        self._make_circle('Proches Test', members=[self.friend])
        level = self.owner_profile.get_visibility_level_for(self.friend)
        self.assertIn('Proches Test', level)

    # ── circle_count et ensure_circle ─────────────────────────────────────────

    def test_circle_count_updates(self):
        """circle_count est incrémenté à la création d'un cercle."""
        before = self.owner_profile.circle_count
        self._make_circle('Count Test Circle')
        self.owner_profile.invalidate_recordset(['circle_count'])
        self.assertGreater(self.owner_profile.circle_count, before)

    def test_ensure_circle_custom_sequence(self):
        """ensure_circle crée un cercle avec la séquence donnée."""
        circle = self.owner_profile.ensure_circle('Seq Circle', sequence=50)
        self.assertEqual(circle.sequence, 50)

    def test_ensure_circle_existing_not_overwritten(self):
        """ensure_circle retourne l'existant sans modifier la séquence."""
        c1 = self.owner_profile.ensure_circle('Stable', sequence=20)
        c2 = self.owner_profile.ensure_circle('Stable', sequence=99)
        self.assertEqual(c1, c2)
        self.assertEqual(c1.sequence, 20)

    def test_duplicate_name_different_profiles_allowed(self):
        """Deux profils différents peuvent avoir des cercles de même nom."""
        other_user = self.env['res.users'].create({
            'name': 'Other Owner', 'login': 'circ_other_owner', 'email': 'other@circles.test',
            'group_ids': [(4, self.env.ref('social_base.group_social_user').id)],
        })
        other_profile = self.Profile.get_or_create_for_user(other_user)
        self._make_circle('Shared Name')
        other_circle = self.env['social_circles.circle'].sudo().create({
            'profile_id': other_profile.id,
            'name': 'Shared Name',
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
            'name': 'Foreign Circle',
        })
        with self.assertRaises(ValidationError):
            self.owner_profile.write({
                'detailed_visibility': 'specific',
                'detailed_visibility_circle_id': foreign_circle.id,
            })
