from odoo.tests import HttpCase, TransactionCase, tagged


def _make_social_user(env, name, login):
    group_social = env.ref('social_base.group_social_user')
    return env['res.users'].create({
        'name': name, 'login': login, 'email': f'{login}@circles.test',
        'password': 'Test1234!',
        'group_ids': [(4, group_social.id)],
    })


@tagged('social_circles', 'circles_portal')
class TestCirclesPortalData(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.owner = _make_social_user(cls.env, 'CirclePortalOwner', 'cp_owner')
        cls.member = _make_social_user(cls.env, 'CirclePortalMember', 'cp_member')
        cls.profile = cls.env['club_social_profile.profile'].sudo().create({
            'user_id': cls.owner.id,
        })

    def test_create_circle(self):
        circle = self.env['social_circles.circle'].sudo().create({
            'profile_id': self.profile.id,
            'name': 'Portal Test Circle',
        })
        self.assertEqual(circle.profile_id, self.profile)

    def test_duplicate_circle_name_raises(self):
        from odoo.exceptions import ValidationError
        self.env['social_circles.circle'].sudo().create({
            'profile_id': self.profile.id, 'name': 'Unique Circle',
        })
        with self.assertRaises(ValidationError):
            self.env['social_circles.circle'].sudo().create({
                'profile_id': self.profile.id, 'name': 'Unique Circle',
            })

    def test_add_member_to_circle(self):
        circle = self.env['social_circles.circle'].sudo().create({
            'profile_id': self.profile.id, 'name': 'Add Member Circle',
        })
        circle.add_member(self.member)
        self.assertIn(self.member, circle.member_ids)

    def test_remove_member_from_circle(self):
        circle = self.env['social_circles.circle'].sudo().create({
            'profile_id': self.profile.id, 'name': 'Remove Member Circle',
        })
        circle.add_member(self.member)
        circle.remove_member(self.member)
        self.assertNotIn(self.member, circle.member_ids)

    def test_delete_circle(self):
        circle = self.env['social_circles.circle'].sudo().create({
            'profile_id': self.profile.id, 'name': 'To Delete Circle',
        })
        circle_id = circle.id
        circle.sudo().unlink()
        self.assertFalse(self.env['social_circles.circle'].sudo().browse(circle_id).exists())

    def test_circle_owner_only_can_delete(self):
        from odoo.exceptions import AccessError
        circle = self.env['social_circles.circle'].sudo().create({
            'profile_id': self.profile.id, 'name': 'Protected Circle',
        })
        with self.assertRaises(AccessError):
            circle.with_user(self.member).unlink()

    def test_member_count_computed(self):
        circle = self.env['social_circles.circle'].sudo().create({
            'profile_id': self.profile.id, 'name': 'Count Circle',
        })
        circle.add_member(self.member)
        self.assertEqual(circle.member_count, 1)


@tagged('social_circles', 'circles_portal', 'post_install', '-at_install')
class TestCirclesPortalHttp(HttpCase):

    def test_my_circles_unauthenticated_redirects(self):
        resp = self.url_open('/my/circles', allow_redirects=False)
        self.assertIn(resp.status_code, (302, 303))

    def test_my_circles_authenticated_ok(self):
        self.authenticate('admin', 'admin')
        resp = self.url_open('/my/circles')
        self.assertEqual(resp.status_code, 200)

    def test_circle_create_post_redirects(self):
        self.authenticate('admin', 'admin')
        resp = self.url_open(
            '/my/circles/create',
            data={'csrf_token': self.csrf_token(), 'name': 'HTTP Test Circle'},
            allow_redirects=False,
        )
        self.assertIn(resp.status_code, (302, 303))

    def test_circle_delete_forbidden_for_non_owner(self):
        admin = self.env.ref('base.user_admin')
        profile = self.env['club_social_profile.profile'].sudo().search(
            [('user_id', '=', admin.id)], limit=1
        ) or self.env['club_social_profile.profile'].sudo().create({'user_id': admin.id})
        circle = self.env['social_circles.circle'].sudo().create({
            'profile_id': profile.id, 'name': 'HTTP Delete Circle',
        })
        other = self.env['res.users'].sudo().create({
            'name': 'HTTP Circle Other', 'login': 'http_circ_other',
            'email': 'http_circ@circles.test', 'password': 'Test1234!',
            'group_ids': [(4, self.env.ref('base.group_portal').id)],
        })
        self.authenticate('http_circ_other', 'Test1234!')
        resp = self.url_open(
            f'/my/circles/{circle.id}/delete',
            data={'csrf_token': self.csrf_token()},
            allow_redirects=False,
        )
        self.assertIn(resp.status_code, (302, 303, 403))
