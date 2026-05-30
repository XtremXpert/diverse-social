from odoo.tests import TransactionCase, tagged
from odoo.exceptions import ValidationError


@tagged('social_base', 'comment')
class TestSocialComment(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = cls.env['res.users'].create({
            'name': 'Comment Test User', 'login': 'comment_test_user', 'email': 'comment@test.test',
            'group_ids': [
                (4, cls.env.ref('base.group_user').id),
                (4, cls.env.ref('social_base.group_social_user').id),
            ],
        })
        cls.post = cls.env['social_base.post'].with_user(cls.user).create({
            'content': 'A post',
        })

    def _make_comment(self, content='Nice!', parent=None):
        vals = {'content': content, 'post_id': self.post.id, 'author_id': self.user.id}
        if parent:
            vals['parent_id'] = parent.id
        return self.env['social_base.comment'].create(vals)

    def test_comment_created_published(self):
        comment = self._make_comment()
        self.assertEqual(comment.state, 'published')

    def test_hide_and_restore(self):
        comment = self._make_comment()
        comment.action_hide()
        self.assertEqual(comment.state, 'hidden')
        comment.action_restore()
        self.assertEqual(comment.state, 'published')

    def test_threaded_reply(self):
        parent = self._make_comment('Parent')
        reply = self._make_comment('Reply', parent=parent)
        self.assertEqual(reply.parent_id, parent)
        self.assertIn(reply, parent.child_ids)

    def test_nesting_limit(self):
        c1 = self._make_comment('L1')
        c2 = self._make_comment('L2', parent=c1)
        c3 = self._make_comment('L3', parent=c2)
        with self.assertRaises(ValidationError):
            self._make_comment('L4', parent=c3)

    def test_cross_post_parent_rejected(self):
        other_post = self.env['social_base.post'].with_user(self.user).create({'content': 'Other'})
        parent = self._make_comment('Parent')
        with self.assertRaises(ValidationError):
            self.env['social_base.comment'].create({
                'content': 'Bad reply',
                'post_id': other_post.id,
                'author_id': self.user.id,
                'parent_id': parent.id,
            })

    def test_delete_comment(self):
        comment = self._make_comment()
        comment.action_delete()
        self.assertEqual(comment.state, 'deleted')

    def test_restore_from_hidden(self):
        comment = self._make_comment()
        comment.action_hide()
        comment.action_restore()
        self.assertEqual(comment.state, 'published')

    def test_nesting_depth_3_valid(self):
        """Three nesting levels (L1→L2→L3) are allowed."""
        c1 = self._make_comment('L1')
        c2 = self._make_comment('L2', parent=c1)
        c3 = self._make_comment('L3', parent=c2)
        self.assertEqual(c3.parent_id, c2)

    def test_comment_like_count(self):
        comment = self._make_comment()
        self.env['social_base.reaction'].create({
            'comment_id': comment.id, 'user_id': self.user.id, 'type': 'like',
        })
        self.assertEqual(comment.like_count, 1)

    def test_comment_count_on_post(self):
        self.env['social_base.comment'].create([
            {'content': f'C{i}', 'post_id': self.post.id, 'author_id': self.user.id}
            for i in range(3)
        ])
        self.assertGreaterEqual(self.post.comment_count, 3)

    def test_cascade_delete_with_post(self):
        comment = self._make_comment('Will be deleted')
        comment_id = comment.id
        post = self.env['social_base.post'].with_user(self.user).create({'content': 'Temp post'})
        child_comment = self.env['social_base.comment'].create({
            'content': 'Child', 'post_id': post.id, 'author_id': self.user.id,
        })
        child_id = child_comment.id
        post.sudo().unlink()
        self.assertFalse(self.env['social_base.comment'].browse(child_id).exists())
