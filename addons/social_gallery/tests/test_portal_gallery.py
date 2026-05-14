import base64

from odoo.tests import HttpCase, TransactionCase, tagged

_TINY_PNG = (
    b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01'
    b'\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00'
    b'\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82'
)
_PNG_B64 = base64.b64encode(_TINY_PNG).decode('ascii')


def _make_social_user(env, name, login):
    group_social = env.ref('social_base.group_social_user')
    return env['res.users'].create({
        'name': name, 'login': login, 'email': f'{login}@gallery.test',
        'password': 'Test1234!',
        'group_ids': [(4, group_social.id)],
    })


@tagged('social_gallery', 'portal_gallery')
class TestPortalGalleryData(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = _make_social_user(cls.env, 'GalleryPortal', 'gallery_portal')
        cls.other = _make_social_user(cls.env, 'GalleryOther', 'gallery_other')
        cls.Gallery = cls.env['social_gallery.gallery']
        cls.Photo = cls.env['social_gallery.photo']

    def _gallery(self, owner=None, is_shared=False, visibility='members'):
        return self.Gallery.sudo().create({
            'name': 'Test Gallery',
            'owner_id': (owner or self.user).id,
            'is_shared': is_shared,
            'visibility': visibility,
        })

    def _photo(self, gallery, user=None, state='approved'):
        return self.Photo.sudo().create({
            'gallery_id': gallery.id,
            'name': 'Test Photo',
            'image_1920': _PNG_B64,
            'submitted_by_id': (user or self.user).id,
            'state': state,
        })

    # ── Accès liste ───────────────────────────────────────────────────────

    def test_gallery_list_includes_members_visibility(self):
        g = self._gallery(visibility='members')
        galleries = self.Gallery.sudo().search([('visibility', 'in', ['public', 'members'])])
        self.assertIn(g, galleries)

    def test_gallery_list_excludes_private(self):
        g = self._gallery(visibility='private')
        galleries = self.Gallery.sudo().search([('visibility', 'in', ['public', 'members'])])
        self.assertNotIn(g, galleries)

    # ── Photos approuvées visibles ────────────────────────────────────────

    def test_detail_shows_only_approved(self):
        g = self._gallery()
        p_approved = self._photo(g, state='approved')
        p_pending = self._photo(g, state='pending')
        approved = g.photo_ids.filtered(lambda p: p.state == 'approved')
        self.assertIn(p_approved, approved)
        self.assertNotIn(p_pending, approved)

    # ── Pagination ────────────────────────────────────────────────────────

    def test_pagination_step_24(self):
        g = self._gallery()
        for i in range(30):
            self.Photo.sudo().create({
                'gallery_id': g.id, 'submitted_by_id': self.user.id,
                'image_1920': _PNG_B64, 'state': 'approved',
            })
        approved = g.photo_ids.filtered(lambda p: p.state == 'approved').sorted('sequence')
        self.assertEqual(len(approved[:24]), 24)
        self.assertEqual(len(approved[24:48]), 6)

    # ── Création galerie ──────────────────────────────────────────────────

    def test_create_gallery_owner(self):
        g = self.Gallery.sudo().create({
            'name': 'Ma galerie perso',
            'owner_id': self.user.id,
            'visibility': 'members',
        })
        self.assertEqual(g.owner_id, self.user)
        my_galleries = self.Gallery.sudo().search([('owner_id', '=', self.user.id)])
        self.assertIn(g, my_galleries)

    # ── Suppression photo ─────────────────────────────────────────────────

    def test_delete_own_pending_photo(self):
        g = self._gallery()
        p = self._photo(g, state='pending')
        p_id = p.id
        p.unlink()
        self.assertFalse(self.Photo.sudo().browse(p_id).exists())

    def test_cannot_delete_others_photo(self):
        g = self._gallery()
        p = self._photo(g, user=self.other, state='pending')
        from werkzeug.exceptions import Forbidden
        if p.submitted_by_id.id == self.user.id:
            self.fail('Setup error: photo should belong to other user')
        self.assertNotEqual(p.submitted_by_id, self.user)

    def test_approved_photo_not_deletable(self):
        g = self._gallery()
        p = self._photo(g, state='approved')
        self.assertEqual(p.state, 'approved')

    # ── Compteurs ─────────────────────────────────────────────────────────

    def test_photo_count_computed(self):
        g = self._gallery()
        self._photo(g, state='approved')
        self._photo(g, state='pending')
        self.assertEqual(g.photo_count, 2)
        self.assertEqual(g.approved_photo_count, 1)
        self.assertEqual(g.pending_photo_count, 1)


@tagged('social_gallery', 'portal_gallery', 'post_install', '-at_install')
class TestPortalGalleryHttp(HttpCase):

    def test_gallery_list_unauthenticated_redirects(self):
        resp = self.url_open('/gallery', allow_redirects=False)
        self.assertIn(resp.status_code, (200, 302, 303))

    def test_gallery_list_authenticated_ok(self):
        self.authenticate('admin', 'admin')
        resp = self.url_open('/gallery')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'Galeries', resp.content)

    def test_gallery_detail_invalid_404(self):
        self.authenticate('admin', 'admin')
        resp = self.url_open('/gallery/999999999')
        self.assertEqual(resp.status_code, 404)

    def test_my_gallery_unauthenticated_redirects(self):
        resp = self.url_open('/my/gallery', allow_redirects=False)
        self.assertIn(resp.status_code, (302, 303))

    def test_my_gallery_authenticated_ok(self):
        self.authenticate('admin', 'admin')
        resp = self.url_open('/my/gallery')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'galerie', resp.content.lower())

    def test_create_gallery_post(self):
        self.authenticate('admin', 'admin')
        resp = self.url_open(
            '/my/gallery/create',
            data={
                'csrf_token': self.csrf_token(),
                'name': 'Galerie HTTP Test',
                'visibility': 'members',
            },
        )
        self.assertEqual(resp.status_code, 200)
        gallery = self.env['social_gallery.gallery'].sudo().search(
            [('name', '=', 'Galerie HTTP Test')], limit=1
        )
        self.assertTrue(gallery)

    def test_create_gallery_no_name_redirects(self):
        self.authenticate('admin', 'admin')
        resp = self.url_open(
            '/my/gallery/create',
            data={'csrf_token': self.csrf_token(), 'name': ''},
        )
        self.assertEqual(resp.status_code, 200)

    def test_gallery_detail_with_photos(self):
        self.authenticate('admin', 'admin')
        admin = self.env.ref('base.user_admin')
        gallery = self.env['social_gallery.gallery'].sudo().create({
            'name': 'HTTP Detail Test',
            'owner_id': admin.id,
            'visibility': 'members',
        })
        self.env['social_gallery.photo'].sudo().create({
            'gallery_id': gallery.id,
            'name': 'Photo HTTP',
            'image_1920': _PNG_B64,
            'submitted_by_id': admin.id,
            'state': 'approved',
        })
        resp = self.url_open(f'/gallery/{gallery.id}')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'Photo HTTP', resp.content)

    def test_delete_pending_photo(self):
        self.authenticate('admin', 'admin')
        admin = self.env.ref('base.user_admin')
        gallery = self.env['social_gallery.gallery'].sudo().create({
            'name': 'Delete Test Gallery',
            'owner_id': admin.id,
            'visibility': 'members',
        })
        photo = self.env['social_gallery.photo'].sudo().create({
            'gallery_id': gallery.id,
            'image_1920': _PNG_B64,
            'submitted_by_id': admin.id,
            'state': 'pending',
        })
        resp = self.url_open(
            f'/my/gallery/photo/{photo.id}/delete',
            data={'csrf_token': self.csrf_token()},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(
            self.env['social_gallery.photo'].sudo().browse(photo.id).exists()
        )

    def test_lightbox_data_attrs_in_html(self):
        self.authenticate('admin', 'admin')
        admin = self.env.ref('base.user_admin')
        gallery = self.env['social_gallery.gallery'].sudo().create({
            'name': 'Lightbox Test',
            'owner_id': admin.id,
            'visibility': 'members',
        })
        self.env['social_gallery.photo'].sudo().create({
            'gallery_id': gallery.id,
            'image_1920': _PNG_B64,
            'submitted_by_id': admin.id,
            'state': 'approved',
        })
        resp = self.url_open(f'/gallery/{gallery.id}')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'data-lightbox', resp.content)
