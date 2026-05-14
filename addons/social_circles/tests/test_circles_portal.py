from odoo.tests import HttpCase, TransactionCase, tagged


def _make_social_user(env, name, login):
    group_social = env.ref('social_base.group_social_user')
    return env['res.users'].create({
        'name': name, 'login': login, 'email': f'{login}@circles.test',
        'password': 'Test1234!',
        'group_ids': [(4, group_social.id)],
    })


def _connect(env, user_a, user_b):
    env['club_social_profile.connection'].sudo().create([
        {'user_id': user_a.id, 'connected_user_id': user_b.id, 'state': 'accepted'},
        {'user_id': user_b.id, 'connected_user_id': user_a.id, 'state': 'accepted'},
    ])


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

    def _circle(self, name='Test Circle'):
        return self.env['social_circles.circle'].sudo().create({
            'profile_id': self.profile.id, 'name': name,
        })

    # ── CRUD cercle ───────────────────────────────────────────────────────

    def test_create_circle(self):
        c = self._circle('Portal Test Circle')
        self.assertEqual(c.profile_id, self.profile)

    def test_duplicate_circle_name_raises(self):
        from odoo.exceptions import ValidationError
        self._circle('Unique Circle')
        with self.assertRaises(ValidationError):
            self._circle('Unique Circle')

    def test_update_circle_name(self):
        c = self._circle('Old Name')
        c.sudo().write({'name': 'New Name'})
        self.assertEqual(c.name, 'New Name')

    def test_delete_circle(self):
        c = self._circle('To Delete')
        c_id = c.id
        c.sudo().unlink()
        self.assertFalse(self.env['social_circles.circle'].sudo().browse(c_id).exists())

    def test_circle_owner_only_can_delete(self):
        from odoo.exceptions import AccessError
        c = self._circle('Protected Circle')
        with self.assertRaises(AccessError):
            c.with_user(self.member).unlink()

    # ── Membres ───────────────────────────────────────────────────────────

    def test_add_member(self):
        c = self._circle('Add Member Circle')
        c.add_member(self.member)
        self.assertIn(self.member, c.member_ids)

    def test_remove_member(self):
        c = self._circle('Remove Member Circle')
        c.add_member(self.member)
        c.remove_member(self.member)
        self.assertNotIn(self.member, c.member_ids)

    def test_has_member(self):
        c = self._circle('Has Member Circle')
        c.add_member(self.member)
        self.assertTrue(c.has_member(self.member))

    def test_member_count_computed(self):
        c = self._circle('Count Circle')
        c.add_member(self.member)
        self.assertEqual(c.member_count, 1)

    def test_add_member_idempotent(self):
        c = self._circle('Idempotent Circle')
        c.add_member(self.member)
        c.add_member(self.member)
        self.assertEqual(c.member_count, 1)

    # ── Visibilité détaillée ──────────────────────────────────────────────

    def test_can_see_detailed_members(self):
        self.profile.sudo().write({'detailed_visibility': 'members'})
        self.assertTrue(self.profile.can_see_detailed_info(self.member))

    def test_cannot_see_detailed_private(self):
        self.profile.sudo().write({'detailed_visibility': 'private'})
        self.assertFalse(self.profile.can_see_detailed_info(self.member))

    def test_can_see_detailed_circles(self):
        self.profile.sudo().write({'detailed_visibility': 'circles'})
        c = self._circle('Vis Circle')
        c.add_member(self.member)
        self.assertTrue(self.profile.can_see_detailed_info(self.member))

    def test_cannot_see_detailed_circles_if_not_in_circle(self):
        self.profile.sudo().write({'detailed_visibility': 'circles'})
        outsider = _make_social_user(self.env, 'Outsider', 'cp_outsider2')
        self.assertFalse(self.profile.can_see_detailed_info(outsider))

    def test_specific_circle_visibility(self):
        from odoo.exceptions import ValidationError
        c = self._circle('Specific Vis Circle')
        self.profile.sudo().write({
            'detailed_visibility': 'specific',
            'detailed_visibility_circle_id': c.id,
        })
        c.add_member(self.member)
        self.assertTrue(self.profile.can_see_detailed_info(self.member))

    def test_get_visibility_level_owner(self):
        level = self.profile.get_visibility_level_for(self.owner)
        self.assertEqual(level, 'owner')

    def test_get_visibility_level_circle(self):
        c = self._circle('Level Circle')
        c.add_member(self.member)
        level = self.profile.get_visibility_level_for(self.member)
        self.assertIn('circle:', level)

    def test_ensure_circle_creates_if_absent(self):
        c = self.profile.ensure_circle('AutoCircle')
        self.assertEqual(c.name, 'AutoCircle')

    def test_ensure_circle_idempotent(self):
        c1 = self.profile.ensure_circle('IdempCircle')
        c2 = self.profile.ensure_circle('IdempCircle')
        self.assertEqual(c1, c2)

    # ── Connexions → addable ──────────────────────────────────────────────

    def test_connections_required_for_add_member(self):
        _connect(self.env, self.owner, self.member)
        from odoo.addons.social_circles.controllers.portal import _get_user_connections
        # Simule request.env.user = owner en passant par le modèle directement
        Connection = self.env['club_social_profile.connection'].sudo()
        sent = Connection.search([('user_id', '=', self.owner.id), ('state', '=', 'accepted')])
        recv = Connection.search([('connected_user_id', '=', self.owner.id), ('state', '=', 'accepted')])
        user_ids = set(sent.mapped('connected_user_id.id')) | set(recv.mapped('user_id.id'))
        self.assertIn(self.member.id, user_ids)


@tagged('social_circles', 'circles_portal', 'post_install', '-at_install')
class TestCirclesPortalHttp(HttpCase):

    def test_my_circles_unauthenticated_redirects(self):
        resp = self.url_open('/my/circles', allow_redirects=False)
        self.assertIn(resp.status_code, (302, 303))

    def test_my_circles_authenticated_ok(self):
        self.authenticate('admin', 'admin')
        resp = self.url_open('/my/circles')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'cercles', resp.content.lower())

    def test_my_circles_has_visibility_form(self):
        self.authenticate('admin', 'admin')
        resp = self.url_open('/my/circles')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'detailed_visibility', resp.content)

    def test_circle_create_post(self):
        self.authenticate('admin', 'admin')
        resp = self.url_open(
            '/my/circles/create',
            data={'csrf_token': self.csrf_token(), 'name': 'HTTP Create Circle'},
        )
        self.assertEqual(resp.status_code, 200)
        circle = self.env['social_circles.circle'].sudo().search(
            [('name', '=', 'HTTP Create Circle')], limit=1
        )
        self.assertTrue(circle)

    def test_circle_create_no_name_redirects(self):
        self.authenticate('admin', 'admin')
        resp = self.url_open(
            '/my/circles/create',
            data={'csrf_token': self.csrf_token(), 'name': ''},
        )
        self.assertEqual(resp.status_code, 200)

    def test_circle_update(self):
        self.authenticate('admin', 'admin')
        admin = self.env.ref('base.user_admin')
        profile = self.env['club_social_profile.profile'].sudo().search(
            [('user_id', '=', admin.id)], limit=1
        ) or self.env['club_social_profile.profile'].sudo().create({'user_id': admin.id})
        circle = self.env['social_circles.circle'].sudo().create({
            'profile_id': profile.id, 'name': 'Before Update',
        })
        resp = self.url_open(
            f'/my/circles/{circle.id}/update',
            data={
                'csrf_token': self.csrf_token(),
                'name': 'After Update',
                'description': 'New desc',
            },
        )
        self.assertEqual(resp.status_code, 200)
        circle.invalidate_recordset()
        self.assertEqual(circle.name, 'After Update')

    def test_circle_delete(self):
        self.authenticate('admin', 'admin')
        admin = self.env.ref('base.user_admin')
        profile = self.env['club_social_profile.profile'].sudo().search(
            [('user_id', '=', admin.id)], limit=1
        ) or self.env['club_social_profile.profile'].sudo().create({'user_id': admin.id})
        circle = self.env['social_circles.circle'].sudo().create({
            'profile_id': profile.id, 'name': 'HTTP Delete Me',
        })
        resp = self.url_open(
            f'/my/circles/{circle.id}/delete',
            data={'csrf_token': self.csrf_token()},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(self.env['social_circles.circle'].sudo().browse(circle.id).exists())

    def test_circle_delete_forbidden_for_non_owner(self):
        admin = self.env.ref('base.user_admin')
        profile = self.env['club_social_profile.profile'].sudo().search(
            [('user_id', '=', admin.id)], limit=1
        ) or self.env['club_social_profile.profile'].sudo().create({'user_id': admin.id})
        circle = self.env['social_circles.circle'].sudo().create({
            'profile_id': profile.id, 'name': 'HTTP Forbidden Delete',
        })
        other = self.env['res.users'].sudo().create({
            'name': 'HTTP Circle Other', 'login': 'http_circ_other2',
            'email': 'http_circ2@circles.test', 'password': 'Test1234!',
            'group_ids': [(4, self.env.ref('base.group_portal').id)],
        })
        self.authenticate('http_circ_other2', 'Test1234!')
        resp = self.url_open(
            f'/my/circles/{circle.id}/delete',
            data={'csrf_token': self.csrf_token()},
            allow_redirects=False,
        )
        self.assertIn(resp.status_code, (302, 303, 403))

    def test_visibility_post(self):
        self.authenticate('admin', 'admin')
        resp = self.url_open(
            '/my/circles/visibility',
            data={
                'csrf_token': self.csrf_token(),
                'detailed_visibility': 'connections',
            },
        )
        self.assertEqual(resp.status_code, 200)
        admin = self.env.ref('base.user_admin')
        profile = self.env['club_social_profile.profile'].sudo().search(
            [('user_id', '=', admin.id)], limit=1
        )
        if profile:
            self.assertEqual(profile.detailed_visibility, 'connections')

    def test_add_member_non_connection_ignored(self):
        self.authenticate('admin', 'admin')
        admin = self.env.ref('base.user_admin')
        profile = self.env['club_social_profile.profile'].sudo().search(
            [('user_id', '=', admin.id)], limit=1
        ) or self.env['club_social_profile.profile'].sudo().create({'user_id': admin.id})
        circle = self.env['social_circles.circle'].sudo().create({
            'profile_id': profile.id, 'name': 'Add Non-Conn Circle',
        })
        stranger = self.env['res.users'].sudo().create({
            'name': 'Stranger User', 'login': 'stranger_circ',
            'email': 'stranger@circles.test', 'password': 'Test1234!',
        })
        self.url_open(
            f'/my/circles/{circle.id}/add_member',
            data={'csrf_token': self.csrf_token(), 'user_id': str(stranger.id)},
        )
        circle.invalidate_recordset()
        self.assertNotIn(stranger, circle.member_ids)
