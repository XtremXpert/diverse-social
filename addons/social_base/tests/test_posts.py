from odoo.tests import TransactionCase, tagged


@tagged('social_base', 'post')
class TestSocialPost(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = cls.env['res.users'].create({
            'name': 'Post Test User', 'login': 'post_test_user', 'email': 'post@test.test',
            'group_ids': [(4, cls.env.ref('social_base.group_social_user').id)],
        })
        cls.Post = cls.env['social_base.post']

    def _make_post(self, content='Test content', visibility='members'):
        return self.Post.with_user(self.user).create({
            'content': content,
            'visibility': visibility,
        })

    def test_create_post(self):
        post = self._make_post()
        self.assertEqual(post.state, 'published')
        self.assertEqual(post.author_id, self.user)

    def test_empty_post_raises(self):
        from odoo.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            self.Post.with_user(self.user).create({'content': '<p></p>'})

    def test_publish_archive_cycle(self):
        post = self._make_post()
        post.action_archive()
        self.assertEqual(post.state, 'archived')
        post.action_publish()
        self.assertEqual(post.state, 'published')

    def test_view_count_increments(self):
        post = self._make_post()
        post.increment_view_count()
        post.increment_view_count()
        self.assertEqual(post.view_count, 2)

    def test_media_type_text(self):
        post = self._make_post()
        self.assertEqual(post.media_type, 'text')

    def test_media_type_photo(self):
        post = self._make_post()
        self.env['ir.attachment'].sudo().create({
            'name': 'img.jpg', 'res_model': 'social_base.post', 'res_id': post.id,
            'mimetype': 'image/jpeg', 'datas': b'',
        })
        post._compute_media_type()
        self.assertEqual(post.media_type, 'photo')

    def test_media_type_video(self):
        post = self._make_post()
        self.env['ir.attachment'].sudo().create({
            'name': 'clip.mp4', 'res_model': 'social_base.post', 'res_id': post.id,
            'mimetype': 'video/mp4', 'datas': b'',
        })
        post._compute_media_type()
        self.assertEqual(post.media_type, 'video')

    def test_media_type_mixed(self):
        post = self._make_post()
        self.env['ir.attachment'].sudo().create([
            {'name': 'img.jpg', 'res_model': 'social_base.post', 'res_id': post.id,
             'mimetype': 'image/jpeg', 'datas': b''},
            {'name': 'clip.mp4', 'res_model': 'social_base.post', 'res_id': post.id,
             'mimetype': 'video/mp4', 'datas': b''},
        ])
        post._compute_media_type()
        self.assertEqual(post.media_type, 'mixed')

    def test_post_with_attachment_no_text_valid(self):
        att = self.env['ir.attachment'].sudo().create({
            'name': 'img.jpg', 'mimetype': 'image/jpeg', 'datas': b'',
        })
        post = self.Post.sudo().create({
            'author_id': self.user.id,
            'content': 'temp',
        })
        att.sudo().write({'res_model': 'social_base.post', 'res_id': post.id})
        post.sudo().write({'content': ''})
        self.assertTrue(post)

    # ── Engagement ────────────────────────────────────────────────────────────

    def test_like_count_computed(self):
        post = self._make_post()
        self.env['social_base.reaction'].create({
            'post_id': post.id, 'user_id': self.user.id, 'type': 'like',
        })
        self.assertEqual(post.like_count, 1)

    def test_non_like_reaction_not_counted_as_like(self):
        post = self._make_post()
        self.env['social_base.reaction'].create({
            'post_id': post.id, 'user_id': self.user.id, 'type': 'love',
        })
        self.assertEqual(post.like_count, 0)

    def test_comment_count_computed(self):
        post = self._make_post()
        self.env['social_base.comment'].create({
            'content': 'A comment', 'post_id': post.id, 'author_id': self.user.id,
        })
        self.assertEqual(post.comment_count, 1)

    def test_share_count_increments(self):
        post = self._make_post()
        post.increment_share_count()
        post.increment_share_count()
        self.assertEqual(post.share_count, 2)

    # ── Modération ────────────────────────────────────────────────────────────

    def test_submit_moderation(self):
        post = self._make_post()
        post.action_submit_moderation()
        self.assertEqual(post.state, 'moderation')

    def test_approve_post(self):
        post = self._make_post()
        post.action_submit_moderation()
        post.action_approve()
        self.assertEqual(post.state, 'published')
        self.assertEqual(post.moderated_by, self.user)
        self.assertTrue(post.moderation_date)

    def test_reject_post(self):
        post = self._make_post()
        post.action_submit_moderation()
        post.action_reject('Contenu inapproprié')
        self.assertEqual(post.state, 'archived')
        self.assertEqual(post.moderation_reason, 'Contenu inapproprié')
        self.assertTrue(post.moderation_date)
