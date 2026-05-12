from odoo.tests import TransactionCase, tagged
from odoo.exceptions import ValidationError


@tagged('social_base', 'comment')
class TestSocialComment(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = cls.env.ref('base.user_demo')
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
