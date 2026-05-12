from odoo.tests import TransactionCase, tagged
from odoo.exceptions import ValidationError


@tagged('social_group', 'group')
class TestSocialGroup(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user1 = cls.env.ref('base.user_demo')
        cls.user2 = cls.env['res.users'].create({
            'name': 'Test User 2', 'login': 'test_user2_sg', 'email': 'test2@sg.test',
        })
        cls.Group = cls.env['social_group.group']

    def _make_group(self, privacy='public', join_type='open'):
        return self.Group.with_user(self.user1).create({
            'name': 'Test Group',
            'privacy': privacy,
            'join_type': join_type,
            'member_ids': [(4, self.user1.id)],
            'admin_ids': [(4, self.user1.id)],
        })

    def test_create_group(self):
        group = self._make_group()
        self.assertEqual(group.creator_id, self.user1)
        self.assertIn(self.user1, group.member_ids)

    def test_join_open_group(self):
        group = self._make_group(privacy='public', join_type='open')
        group.with_user(self.user2).action_join()
        self.assertIn(self.user2, group.member_ids)

    def test_join_approval_creates_request(self):
        group = self._make_group(privacy='private', join_type='approval')
        group.with_user(self.user2).action_join()
        request = self.env['social_group.join_request'].search([
            ('group_id', '=', group.id), ('user_id', '=', self.user2.id),
        ])
        self.assertEqual(request.state, 'pending')

    def test_approve_join_request(self):
        group = self._make_group(privacy='private', join_type='approval')
        group.with_user(self.user2).action_join()
        req = self.env['social_group.join_request'].search([('group_id', '=', group.id)])
        req.with_user(self.user1).action_approve()
        self.assertIn(self.user2, group.member_ids)
        self.assertEqual(req.state, 'approved')

    def test_invite_only_raises(self):
        group = self._make_group(join_type='invite')
        with self.assertRaises(ValidationError):
            group.with_user(self.user2).action_join()

    def test_sole_admin_cannot_leave(self):
        group = self._make_group()
        with self.assertRaises(ValidationError):
            group.with_user(self.user1).action_leave()

    def test_post_linked_to_group(self):
        group = self._make_group()
        post = self.env['social_base.post'].with_user(self.user1).create({
            'content': 'Group post', 'group_id': group.id,
        })
        self.assertIn(post, group.post_ids)
        self.assertEqual(group.post_count, 1)
