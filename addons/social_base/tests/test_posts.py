from odoo.tests import TransactionCase, tagged


@tagged('social_base', 'post')
class TestSocialPost(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = cls.env.ref('base.user_demo')
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
