from odoo.tests import HttpCase, TransactionCase, tagged


def _make_social_user(env, name, login):
    group_social = env.ref('social_base.group_social_user')
    return env['res.users'].create({
        'name': name, 'login': login, 'email': f'{login}@portal.test',
        'password': 'Test1234!',
        'group_ids': [(4, group_social.id)],
    })


@tagged('social_group', 'group_portal')
class TestGroupPortalACL(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = _make_social_user(cls.env, 'GroupUser', 'gp_user')
        cls.other = _make_social_user(cls.env, 'GroupOther', 'gp_other')
        cls.public_group = cls.env['social_group.group'].sudo().create({
            'name': 'Public Test Group',
            'privacy': 'public',
            'join_type': 'open',
            'creator_id': cls.user.id,
        })
        cls.private_group = cls.env['social_group.group'].sudo().create({
            'name': 'Private Test Group',
            'privacy': 'private',
            'join_type': 'approval',
            'creator_id': cls.user.id,
        })
        cls.secret_group = cls.env['social_group.group'].sudo().create({
            'name': 'Secret Test Group',
            'privacy': 'secret',
            'join_type': 'invite',
            'creator_id': cls.user.id,
            'member_ids': [(4, cls.user.id)],
        })

    def test_public_and_private_visible_via_sudo(self):
        groups = self.env['social_group.group'].sudo().search([
            ('privacy', 'in', ['public', 'private']),
        ])
        self.assertIn(self.public_group, groups)
        self.assertIn(self.private_group, groups)

    def test_secret_group_hidden_from_non_member(self):
        # ir.rule: secret groups not visible to non-members
        visible = self.env['social_group.group'].with_user(self.other).search([])
        self.assertNotIn(self.secret_group, visible)

    def test_secret_group_visible_to_member(self):
        visible = self.env['social_group.group'].with_user(self.user).search([
            ('id', '=', self.secret_group.id),
        ])
        self.assertIn(self.secret_group, visible)

    def test_join_open_group_adds_member(self):
        self.public_group.with_user(self.other).action_join()
        self.assertIn(self.other, self.public_group.member_ids)

    def test_join_approval_group_creates_request(self):
        self.private_group.with_user(self.other).action_join()
        req = self.env['social_group.join_request'].sudo().search([
            ('group_id', '=', self.private_group.id),
            ('user_id', '=', self.other.id),
        ], limit=1)
        self.assertTrue(req)
        self.assertEqual(req.state, 'pending')

    def test_leave_group_removes_member(self):
        self.public_group.sudo().write({'member_ids': [(4, self.other.id)]})
        self.public_group.with_user(self.other).action_leave()
        self.assertNotIn(self.other, self.public_group.member_ids)

    def test_my_groups_filtered_by_membership(self):
        self.public_group.sudo().write({'member_ids': [(4, self.user.id)]})
        my_groups = self.env['social_group.group'].with_user(self.user).search([
            ('member_ids', 'in', self.user.id),
        ])
        self.assertIn(self.public_group, my_groups)
        self.assertNotIn(self.private_group, my_groups)

    def test_group_posts_visible_to_member(self):
        self.public_group.sudo().write({'member_ids': [(4, self.user.id)]})
        post = self.env['social_base.post'].sudo().create({
            'name': 'Group Post',
            'content': '<p>hello</p>',
            'author_id': self.user.id,
            'visibility': 'members',
            'state': 'published',
            'group_id': self.public_group.id,
        })
        posts = self.env['social_base.post'].sudo().search([
            ('group_id', '=', self.public_group.id),
            ('state', '=', 'published'),
        ])
        self.assertIn(post, posts)


@tagged('social_group', 'group_portal', 'post_install', '-at_install')
class TestGroupPortalHttp(HttpCase):

    def test_groups_unauthenticated_redirects(self):
        resp = self.url_open('/groups', allow_redirects=False)
        self.assertIn(resp.status_code, (302, 303))

    def test_groups_authenticated_ok(self):
        self.authenticate('admin', 'admin')
        resp = self.url_open('/groups')
        self.assertEqual(resp.status_code, 200)

    def test_group_detail_authenticated_ok(self):
        self.authenticate('admin', 'admin')
        group = self.env['social_group.group'].sudo().search([], limit=1)
        if not group:
            group = self.env['social_group.group'].sudo().create({
                'name': 'HTTP Test Group', 'privacy': 'public',
                'join_type': 'open', 'creator_id': self.env.ref('base.user_admin').id,
            })
        resp = self.url_open(f'/groups/{group.id}')
        self.assertEqual(resp.status_code, 200)

    def test_my_groups_authenticated_ok(self):
        self.authenticate('admin', 'admin')
        resp = self.url_open('/my/groups')
        self.assertEqual(resp.status_code, 200)

    def test_group_join_post_redirects(self):
        self.authenticate('admin', 'admin')
        group = self.env['social_group.group'].sudo().create({
            'name': 'HTTP Join Group', 'privacy': 'public',
            'join_type': 'open',
            'creator_id': self.env.ref('base.user_admin').id,
        })
        resp = self.url_open(
            f'/groups/{group.id}/join',
            data={'csrf_token': self.csrf_token()},
            allow_redirects=False,
        )
        self.assertIn(resp.status_code, (302, 303))
