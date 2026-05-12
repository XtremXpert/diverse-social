from odoo.tests import TransactionCase, tagged


@tagged('social_gallery', 'gallery')
class TestSocialGallery(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = cls.env.ref('base.user_demo')
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
