from odoo.tests import HttpCase, TransactionCase, tagged


def _make_social_user(env, name, login):
    group_user = env.ref('base.group_user')
    group_social = env.ref('social_base.group_social_user')
    return env['res.users'].create({
        'name': name, 'login': login, 'email': f'{login}@portal.test',
        'password': 'Test1234!',
        'group_ids': [(4, group_user.id), (4, group_social.id)],
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
        _csrf = self.csrf_token()
        resp = self.url_open('/groups')
        self.assertEqual(resp.status_code, 200)

    def test_group_detail_authenticated_ok(self):
        self.authenticate('admin', 'admin')
        _csrf = self.csrf_token()
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
        _csrf = self.csrf_token()
        resp = self.url_open('/my/groups')
        self.assertEqual(resp.status_code, 200)

    def test_group_join_post_redirects(self):
        self.authenticate('admin', 'admin')
        _csrf = self.csrf_token()
        group = self.env['social_group.group'].sudo().create({
            'name': 'HTTP Join Group', 'privacy': 'public',
            'join_type': 'open',
            'creator_id': self.env.ref('base.user_admin').id,
        })
        resp = self.url_open(
            f'/groups/{group.id}/join',
            data={'csrf_token': _csrf, },
            allow_redirects=False,
        )
        self.assertIn(resp.status_code, (302, 303))

    # ── Create a group ────────────────────────────────────────────────────

    def test_create_group_ok(self):
        self.authenticate('admin', 'admin')
        _csrf = self.csrf_token()
        resp = self.url_open(
            '/groups/create',
            data={'csrf_token': _csrf, 
                'name': 'HTTP Created Group',
                'description': 'Created from portal',
                'privacy': 'private',
                'join_type': 'approval',
            },
        )
        self.assertEqual(resp.status_code, 200)
        g = self.env['social_group.group'].sudo().search([('name', '=', 'HTTP Created Group')], limit=1)
        self.assertTrue(g)

    def test_create_group_missing_name_redirects_with_error(self):
        self.authenticate('admin', 'admin')
        _csrf = self.csrf_token()
        resp = self.url_open(
            '/groups/create',
            data={'csrf_token': _csrf, 'name': ''},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'name_required', resp.url.encode())

    # ── Edit a group ──────────────────────────────────────────────────────

    def test_edit_group_by_admin(self):
        admin = self.env.ref('base.user_admin')
        group = self.env['social_group.group'].sudo().create({
            'name': 'Edit Test Group', 'privacy': 'public',
            'join_type': 'open', 'creator_id': admin.id,
            'admin_ids': [(4, admin.id)],
        })
        self.authenticate('admin', 'admin')
        _csrf = self.csrf_token()
        resp = self.url_open(
            f'/groups/{group.id}/edit',
            data={'csrf_token': _csrf, 
                'name': 'Edited Group Name',
                'privacy': 'private',
                'join_type': 'approval',
            },
        )
        self.assertEqual(resp.status_code, 200)
        group.invalidate_recordset()
        self.assertEqual(group.name, 'Edited Group Name')
        self.assertEqual(group.privacy, 'private')

    def test_edit_group_by_non_admin_forbidden(self):
        group_user = self.env.ref('base.group_user')
        group_social = self.env.ref('social_base.group_social_user')
        other = self.env['res.users'].create({
            'name': 'NonAdmin', 'login': 'non_admin_http',
            'email': 'non_admin@test.com', 'password': 'Test1234!',
            'group_ids': [(4, group_user.id), (4, group_social.id)],
        })
        admin = self.env.ref('base.user_admin')
        group = self.env['social_group.group'].sudo().create({
            'name': 'Admin Group', 'privacy': 'public',
            'join_type': 'open', 'creator_id': admin.id,
            'admin_ids': [(4, admin.id)],
        })
        self.authenticate('non_admin_http', 'Test1234!')
        _csrf = self.csrf_token()
        resp = self.url_open(
            f'/groups/{group.id}/edit',
            data={'csrf_token': _csrf, 'name': 'Hacked Name'},
        )
        self.assertEqual(resp.status_code, 403)

    # ── Approuver / rejeter les demandes ─────────────────────────────────

    def _make_join_request(self, group, user):
        return self.env['social_group.join_request'].sudo().create({
            'group_id': group.id,
            'user_id': user.id,
            'state': 'pending',
        })

    def test_approve_request_by_creator(self):
        admin = self.env.ref('base.user_admin')
        group_user = self.env.ref('base.group_user')
        group_social = self.env.ref('social_base.group_social_user')
        requester = self.env['res.users'].create({
            'name': 'Requester', 'login': 'requester_http',
            'email': 'req@test.com', 'password': 'Test1234!',
            'group_ids': [(4, group_user.id), (4, group_social.id)],
        })
        group = self.env['social_group.group'].sudo().create({
            'name': 'Approval Group', 'privacy': 'private',
            'join_type': 'approval', 'creator_id': admin.id,
        })
        req = self._make_join_request(group, requester)
        self.authenticate('admin', 'admin')
        _csrf = self.csrf_token()
        resp = self.url_open(
            f'/groups/{group.id}/requests/{req.id}/approve',
            data={'csrf_token': _csrf, },
        )
        self.assertEqual(resp.status_code, 200)
        req.invalidate_recordset()
        self.assertEqual(req.state, 'approved')
        self.assertIn(requester, group.member_ids)

    def test_reject_request_by_creator(self):
        admin = self.env.ref('base.user_admin')
        group_user = self.env.ref('base.group_user')
        group_social = self.env.ref('social_base.group_social_user')
        requester2 = self.env['res.users'].create({
            'name': 'Requester2', 'login': 'requester2_http',
            'email': 'req2@test.com', 'password': 'Test1234!',
            'group_ids': [(4, group_user.id), (4, group_social.id)],
        })
        group = self.env['social_group.group'].sudo().create({
            'name': 'Reject Test Group', 'privacy': 'private',
            'join_type': 'approval', 'creator_id': admin.id,
        })
        req = self._make_join_request(group, requester2)
        self.authenticate('admin', 'admin')
        _csrf = self.csrf_token()
        resp = self.url_open(
            f'/groups/{group.id}/requests/{req.id}/reject',
            data={'csrf_token': _csrf, },
        )
        self.assertEqual(resp.status_code, 200)
        req.invalidate_recordset()
        self.assertEqual(req.state, 'rejected')

    def test_approve_request_by_non_mod_forbidden(self):
        group_user = self.env.ref('base.group_user')
        group_social = self.env.ref('social_base.group_social_user')
        creator = self.env['res.users'].create({
            'name': 'Creator', 'login': 'creator_http',
            'email': 'creator@test.com', 'password': 'Test1234!',
            'group_ids': [(4, group_user.id), (4, group_social.id)],
        })
        requester3 = self.env['res.users'].create({
            'name': 'Requester3', 'login': 'requester3_http',
            'email': 'req3@test.com', 'password': 'Test1234!',
            'group_ids': [(4, group_user.id), (4, group_social.id)],
        })
        group = self.env['social_group.group'].sudo().create({
            'name': 'Non-mod Test Group', 'privacy': 'private',
            'join_type': 'approval', 'creator_id': creator.id,
        })
        req = self._make_join_request(group, requester3)
        # Authenticate as admin who is NOT creator/admin of this group
        # (admin has group_social_moderator by default - let's use a plain member)
        self.authenticate('requester3_http', 'Test1234!')
        _csrf = self.csrf_token()
        resp = self.url_open(
            f'/groups/{group.id}/requests/{req.id}/approve',
            data={'csrf_token': _csrf, },
        )
        self.assertEqual(resp.status_code, 403)

    def test_approve_cross_group_injection_raises(self):
        admin = self.env.ref('base.user_admin')
        group_user = self.env.ref('base.group_user')
        group_social = self.env.ref('social_base.group_social_user')
        other_user = self.env['res.users'].create({
            'name': 'CrossUser', 'login': 'cross_user_http',
            'email': 'cross@test.com', 'password': 'Test1234!',
            'group_ids': [(4, group_user.id), (4, group_social.id)],
        })
        group_a = self.env['social_group.group'].sudo().create({
            'name': 'Group A', 'privacy': 'private',
            'join_type': 'approval', 'creator_id': admin.id,
        })
        group_b = self.env['social_group.group'].sudo().create({
            'name': 'Group B', 'privacy': 'private',
            'join_type': 'approval', 'creator_id': admin.id,
        })
        req_b = self._make_join_request(group_b, other_user)
        self.authenticate('admin', 'admin')
        _csrf = self.csrf_token()
        # Try to approve group_b's request via group_a's URL
        resp = self.url_open(
            f'/groups/{group_a.id}/requests/{req_b.id}/approve',
            data={'csrf_token': _csrf, },
        )
        self.assertEqual(resp.status_code, 404)
        req_b.invalidate_recordset()
        self.assertEqual(req_b.state, 'pending')
