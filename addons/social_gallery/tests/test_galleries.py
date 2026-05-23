from odoo.tests import TransactionCase, tagged


@tagged('social_gallery', 'gallery')
class TestSocialGallery(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = cls.env['res.users'].create({
            'name': 'Gallery Test User', 'login': 'gallery_test_user', 'email': 'gallery@test.test',
            'group_ids': [
                (4, cls.env.ref('base.group_user').id),
                (4, cls.env.ref('social_base.group_social_user').id),
            ],
        })
        cls.Gallery = cls.env['social_gallery.gallery']

    def _make_gallery(self, is_shared=False, visibility='members'):
        return self.Gallery.with_user(self.user).create({
            'name': 'Test Gallery',
            'owner_id': self.user.id,
            'visibility': visibility,
            'is_shared': is_shared,
        })

    def test_create_gallery(self):
        gallery = self._make_gallery()
        self.assertEqual(gallery.owner_id, self.user)
        self.assertEqual(gallery.photo_count, 0)

    def test_add_photo_approved_by_default(self):
        gallery = self._make_gallery()
        photo = self.env['social_gallery.photo'].create({
            'gallery_id': gallery.id,
            'name': 'Test Photo',
            'submitted_by_id': self.user.id,
        })
        self.assertEqual(photo.state, 'approved')
        self.assertEqual(gallery.approved_photo_count, 1)

    def test_shared_gallery_photo_pending(self):
        gallery = self._make_gallery(is_shared=True)
        photo = self.env['social_gallery.photo'].create({
            'gallery_id': gallery.id,
            'submitted_by_id': self.user.id,
            'state': 'pending',
        })
        self.assertEqual(photo.state, 'pending')
        self.assertEqual(gallery.pending_photo_count, 1)
        self.assertEqual(gallery.approved_photo_count, 0)

    def test_approve_photo(self):
        gallery = self._make_gallery(is_shared=True)
        photo = self.env['social_gallery.photo'].create({
            'gallery_id': gallery.id,
            'submitted_by_id': self.user.id,
            'state': 'pending',
        })
        photo.action_approve()
        self.assertEqual(photo.state, 'approved')
        self.assertEqual(gallery.approved_photo_count, 1)

    def test_reject_photo(self):
        gallery = self._make_gallery(is_shared=True)
        photo = self.env['social_gallery.photo'].create({
            'gallery_id': gallery.id,
            'submitted_by_id': self.user.id,
            'state': 'pending',
        })
        photo.action_reject()
        self.assertEqual(photo.state, 'rejected')
        self.assertEqual(gallery.approved_photo_count, 0)
        self.assertEqual(gallery.pending_photo_count, 0)

    def test_approve_sets_moderation_metadata(self):
        gallery = self._make_gallery(is_shared=True)
        photo = self.env['social_gallery.photo'].create({
            'gallery_id': gallery.id,
            'submitted_by_id': self.user.id,
            'state': 'pending',
        })
        photo.sudo().action_approve()
        self.assertTrue(photo.moderated_by_id)
        self.assertTrue(photo.moderation_date)

    def test_reject_sets_moderation_metadata(self):
        gallery = self._make_gallery(is_shared=True)
        photo = self.env['social_gallery.photo'].create({
            'gallery_id': gallery.id,
            'submitted_by_id': self.user.id,
            'state': 'pending',
        })
        photo.sudo().action_reject()
        self.assertTrue(photo.moderated_by_id)
        self.assertTrue(photo.moderation_date)

    def test_photo_count_includes_rejected(self):
        """photo_count compte les photos rejetées aussi."""
        gallery = self._make_gallery()
        self.env['social_gallery.photo'].create({
            'gallery_id': gallery.id,
            'submitted_by_id': self.user.id,
            'state': 'rejected',
        })
        self.assertEqual(gallery.photo_count, 1)
        self.assertEqual(gallery.approved_photo_count, 0)

    def test_cover_photo_field(self):
        """Le champ cover_photo_id accepte une photo approuvée."""
        gallery = self._make_gallery()
        photo = self.env['social_gallery.photo'].create({
            'gallery_id': gallery.id,
            'submitted_by_id': self.user.id,
            'state': 'approved',
        })
        gallery.write({'cover_photo_id': photo.id})
        self.assertEqual(gallery.cover_photo_id, photo)

    def test_gallery_visibility_public(self):
        gallery = self._make_gallery(visibility='public')
        self.assertEqual(gallery.visibility, 'public')

    def test_gallery_visibility_connections(self):
        gallery = self._make_gallery(visibility='connections')
        self.assertEqual(gallery.visibility, 'connections')

    def test_gallery_sequence_order(self):
        """Les galeries sont ordonnées par séquence croissante."""
        g1 = self.Gallery.sudo().create({
            'name': 'Seq A', 'owner_id': self.user.id, 'sequence': 20,
        })
        g2 = self.Gallery.sudo().create({
            'name': 'Seq B', 'owner_id': self.user.id, 'sequence': 10,
        })
        results = self.Gallery.sudo().search([
            ('id', 'in', [g1.id, g2.id])
        ], order='sequence, id')
        self.assertEqual(results[0], g2)
        self.assertEqual(results[1], g1)

    # ── Visibility ────────────────────────────────────────────────────────

    def test_default_visibility_members(self):
        gallery = self.Gallery.with_user(self.user).create({
            'name': 'Default Visibility', 'owner_id': self.user.id,
        })
        self.assertEqual(gallery.visibility, 'members')

    def test_public_accessible_to_portal(self):
        portal_user = self.env['res.users'].create({
            'name': 'Portal Viewer', 'login': 'gallery_portal_viewer',
            'email': 'gportal@test.test',
            'group_ids': [(4, self.env.ref('base.group_portal').id)],
        })
        gallery = self._make_gallery(visibility='public')
        self.assertTrue(gallery.is_accessible_by(portal_user))

    def test_members_accessible_to_internal_only(self):
        other = self.env['res.users'].create({
            'name': 'Other Member', 'login': 'gallery_other_member',
            'email': 'gmember@test.test',
            'group_ids': [
                (4, self.env.ref('base.group_user').id),
                (4, self.env.ref('social_base.group_social_user').id),
            ],
        })
        portal_user = self.env['res.users'].create({
            'name': 'Portal Outsider', 'login': 'gallery_portal_outsider',
            'email': 'goutsider@test.test',
            'group_ids': [(4, self.env.ref('base.group_portal').id)],
        })
        gallery = self._make_gallery(visibility='members')
        self.assertTrue(gallery.is_accessible_by(other))
        self.assertFalse(gallery.is_accessible_by(portal_user))

    def test_connections_accessible_only_to_connections(self):
        friend = self.env['res.users'].create({
            'name': 'Friend', 'login': 'gallery_friend',
            'email': 'gfriend@test.test',
            'group_ids': [
                (4, self.env.ref('base.group_user').id),
                (4, self.env.ref('social_base.group_social_user').id),
            ],
        })
        stranger = self.env['res.users'].create({
            'name': 'Stranger', 'login': 'gallery_stranger',
            'email': 'gstranger@test.test',
            'group_ids': [
                (4, self.env.ref('base.group_user').id),
                (4, self.env.ref('social_base.group_social_user').id),
            ],
        })
        self.env['club_social_profile.connection'].create({
            'user_id': self.user.id,
            'connected_user_id': friend.id,
            'connection_type': 'friend',
            'state': 'accepted',
        })
        gallery = self._make_gallery(visibility='connections')
        self.assertTrue(gallery.is_accessible_by(friend))
        self.assertFalse(gallery.is_accessible_by(stranger))

    def test_owner_always_accesses_own_gallery(self):
        gallery = self._make_gallery(visibility='connections')
        self.assertTrue(gallery.is_accessible_by(self.user))

    def test_reject_then_approve_updates_counts(self):
        """Rejeter puis approuver une photo met à jour les compteurs."""
        gallery = self._make_gallery()
        photo = self.env['social_gallery.photo'].create({
            'gallery_id': gallery.id,
            'submitted_by_id': self.user.id,
            'state': 'pending',
        })
        photo.sudo().action_reject()
        self.assertEqual(gallery.approved_photo_count, 0)
        photo.sudo().write({'state': 'pending'})
        photo.sudo().action_approve()
        self.assertEqual(gallery.approved_photo_count, 1)
