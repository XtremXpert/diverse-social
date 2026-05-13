from odoo.tests import TransactionCase, tagged


@tagged('social_base', 'reaction')
class TestSocialReaction(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = cls.env['res.users'].create({
            'name': 'Reaction Test User', 'login': 'reaction_test_user', 'email': 'reaction@test.test',
            'group_ids': [(4, cls.env.ref('social_base.group_social_user').id)],
        })
        cls.post = cls.env['social_base.post'].with_user(cls.user).create({'content': 'A post'})

    def test_add_reaction(self):
        self.env['social_base.reaction'].create({
            'post_id': self.post.id,
            'user_id': self.user.id,
            'type': 'like',
        })
        self.assertEqual(self.post.like_count, 1)

    def test_duplicate_reaction_updates(self):
        self.env['social_base.reaction'].create({
            'post_id': self.post.id,
            'user_id': self.user.id,
            'type': 'like',
        })
        self.env['social_base.reaction'].create({
            'post_id': self.post.id,
            'user_id': self.user.id,
            'type': 'love',
        })
        reactions = self.env['social_base.reaction'].search([
            ('post_id', '=', self.post.id),
            ('user_id', '=', self.user.id),
        ])
        self.assertEqual(len(reactions), 1)
        self.assertEqual(reactions.type, 'love')

    def test_comment_reaction(self):
        comment = self.env['social_base.comment'].create({
            'content': 'Hi', 'post_id': self.post.id, 'author_id': self.user.id,
        })
        self.env['social_base.reaction'].create({
            'comment_id': comment.id,
            'user_id': self.user.id,
            'type': 'like',
        })
        self.assertEqual(comment.like_count, 1)

    def test_target_compute(self):
        r = self.env['social_base.reaction'].create({
            'post_id': self.post.id,
            'user_id': self.user.id,
            'type': 'wow',
        })
        self.assertEqual(r.target_model, 'social_base.post')
        self.assertEqual(r.target_id, self.post.id)
