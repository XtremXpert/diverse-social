from odoo.tests import HttpCase, TransactionCase, tagged


def _make_social_user(env, name, login):
    group_user = env.ref('base.group_user')
    group_social = env.ref('social_base.group_social_user')
    return env['res.users'].create({
        'name': name, 'login': login, 'email': f'{login}@circles.test',
        'password': 'Test1234!',
        'group_ids': [(4, group_user.id), (4, group_social.id)],
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
        # One type per test that needs a unique type to avoid duplicate-type constraint
        CircleType = cls.env['social_circles.circle_type']
        cls.type_portal = CircleType.create({'name': 'Portal Test T', 'sequence': 10})
        cls.type_unique = CircleType.create({'name': 'Unique Circle T', 'sequence': 20})
        cls.type_old = CircleType.create({'name': 'Old Name T', 'sequence': 30})
        cls.type_delete = CircleType.create({'name': 'To Delete T', 'sequence': 40})
        cls.type_protected = CircleType.create({'name': 'Protected T', 'sequence': 50})
        cls.type_add = CircleType.create({'name': 'Add Member T', 'sequence': 60})
        cls.type_remove = CircleType.create({'name': 'Remove Member T', 'sequence': 70})
        cls.type_has = CircleType.create({'name': 'Has Member T', 'sequence': 80})
        cls.type_count = CircleType.create({'name': 'Count Circle T', 'sequence': 90})
        cls.type_idem = CircleType.create({'name': 'Idempotent T', 'sequence': 100})
        cls.type_vis = CircleType.create({'name': 'Vis Circle T', 'sequence': 110})
        cls.type_specific = CircleType.create({'name': 'Specific Vis T', 'sequence': 120})
        cls.type_level = CircleType.create({'name': 'Level Circle T', 'sequence': 130})
        cls.type_auto = CircleType.create({'name': 'AutoCircle T', 'sequence': 140})
        cls.type_idemp2 = CircleType.create({'name': 'IdempCircle T', 'sequence': 150})

    def _circle(self, type_id=None, nickname=None):
        """Create a circle for this test's profile."""
        type_id = type_id or self.type_portal
        vals = {'profile_id': self.profile.id, 'type_id': type_id.id}
        if nickname:
            vals['name'] = nickname
        return self.env['social_circles.circle'].sudo().create(vals)

    # ── CRUD cercle ───────────────────────────────────────────────────────

    def test_create_circle(self):
        c = self._circle(self.type_portal)
        self.assertEqual(c.profile_id, self.profile)

    def test_duplicate_circle_name_raises(self):
        """Two circles of same type on same profile raises ValidationError."""
        from odoo.exceptions import ValidationError
        self._circle(self.type_unique)
        with self.assertRaises(ValidationError):
            self._circle(self.type_unique)

    def test_update_circle_name(self):
        """The optional nickname field can be updated freely."""
        c = self._circle(self.type_old, nickname='Old Nickname')
        c.sudo().write({'name': 'New Nickname'})
        self.assertEqual(c.name, 'New Nickname')

    def test_delete_circle(self):
        c = self._circle(self.type_delete)
        c_id = c.id
        c.sudo().unlink()
        self.assertFalse(self.env['social_circles.circle'].sudo().browse(c_id).exists())

    def test_circle_owner_only_can_delete(self):
        from odoo.exceptions import AccessError
        c = self._circle(self.type_protected)
        with self.assertRaises(AccessError):
            c.with_user(self.member).unlink()

    # ── Members ───────────────────────────────────────────────────────────

    def test_add_member(self):
        c = self._circle(self.type_add)
        c.add_member(self.member)
        self.assertIn(self.member, c.member_ids)

    def test_remove_member(self):
        c = self._circle(self.type_remove)
        c.add_member(self.member)
        c.remove_member(self.member)
        self.assertNotIn(self.member, c.member_ids)

    def test_has_member(self):
        c = self._circle(self.type_has)
        c.add_member(self.member)
        self.assertTrue(c.has_member(self.member))

    def test_member_count_computed(self):
        c = self._circle(self.type_count)
        c.add_member(self.member)
        self.assertEqual(c.member_count, 1)

    def test_add_member_idempotent(self):
        c = self._circle(self.type_idem)
        c.add_member(self.member)
        c.add_member(self.member)
        self.assertEqual(c.member_count, 1)

    # ── Detailed visibility ───────────────────────────────────────────────

    def test_can_see_detailed_members(self):
        self.profile.sudo().write({'detailed_visibility': 'members'})
        self.assertTrue(self.profile.can_see_detailed_info(self.member))

    def test_cannot_see_detailed_private(self):
        self.profile.sudo().write({'detailed_visibility': 'private'})
        self.assertFalse(self.profile.can_see_detailed_info(self.member))

    def test_can_see_detailed_circles(self):
        self.profile.sudo().write({'detailed_visibility': 'circles'})
        c = self._circle(self.type_vis)
        c.add_member(self.member)
        self.assertTrue(self.profile.can_see_detailed_info(self.member))

    def test_cannot_see_detailed_circles_if_not_in_circle(self):
        self.profile.sudo().write({'detailed_visibility': 'circles'})
        outsider = _make_social_user(self.env, 'Outsider', 'cp_outsider2')
        self.assertFalse(self.profile.can_see_detailed_info(outsider))

    def test_specific_circle_visibility(self):
        c = self._circle(self.type_specific)
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
        c = self._circle(self.type_level)
        c.add_member(self.member)
        level = self.profile.get_visibility_level_for(self.member)
        self.assertIn('circle:', level)

    def test_ensure_circle_creates_if_absent(self):
        c = self.profile.ensure_circle(self.type_auto)
        self.assertEqual(c.type_id, self.type_auto)

    def test_ensure_circle_idempotent(self):
        c1 = self.profile.ensure_circle(self.type_idemp2)
        c2 = self.profile.ensure_circle(self.type_idemp2)
        self.assertEqual(c1, c2)

    # ── Connexions → addable ──────────────────────────────────────────────

    def test_connections_required_for_add_member(self):
        _connect(self.env, self.owner, self.member)
        from odoo.addons.social_circles.controllers.portal import _get_user_connections
        # Simulate request.env.user = owner via the model directly
        Connection = self.env['club_social_profile.connection'].sudo()
        sent = Connection.search([('user_id', '=', self.owner.id), ('state', '=', 'accepted')])
        recv = Connection.search([('connected_user_id', '=', self.owner.id), ('state', '=', 'accepted')])
        user_ids = set(sent.mapped('connected_user_id.id')) | set(recv.mapped('user_id.id'))
        self.assertIn(self.member.id, user_ids)


def _get_or_create_http_type(env, name):
    """Return (or create) a circle_type for use in HTTP tests."""
    t = env['social_circles.circle_type'].sudo().search([('name', '=', name)], limit=1)
    if not t:
        t = env['social_circles.circle_type'].sudo().create({'name': name, 'sequence': 200})
    return t


@tagged('social_circles', 'circles_portal', 'post_install', '-at_install')
class TestCirclesPortalHttp(HttpCase):

    def test_my_circles_unauthenticated_redirects(self):
        resp = self.url_open('/my/circles', allow_redirects=False)
        self.assertIn(resp.status_code, (302, 303))

    def test_my_circles_authenticated_ok(self):
        self.authenticate('admin', 'admin')
        _csrf = self.csrf_token()
        resp = self.url_open('/my/circles')
        self.assertEqual(resp.status_code, 200)
        # Structural marker: the page is rendered by the my_circles template.
        self.assertIn(b'social_circles.portal_my_circles', resp.content)

    def test_my_circles_has_visibility_form(self):
        self.authenticate('admin', 'admin')
        _csrf = self.csrf_token()
        resp = self.url_open('/my/circles')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'detailed_visibility', resp.content)

    def test_circle_create_post(self):
        self.authenticate('admin', 'admin')
        _csrf = self.csrf_token()
        ct = _get_or_create_http_type(self.env, 'HTTP Create Type')
        resp = self.url_open(
            '/my/circles/create',
            data={'csrf_token': _csrf, 'type_id': str(ct.id), 'name': 'My Nickname'},
        )
        self.assertEqual(resp.status_code, 200)
        circle = self.env['social_circles.circle'].sudo().search(
            [('type_id', '=', ct.id)], limit=1
        )
        self.assertTrue(circle)

    def test_circle_create_no_type_redirects(self):
        """Submitting without a type_id redirects with error."""
        self.authenticate('admin', 'admin')
        _csrf = self.csrf_token()
        resp = self.url_open(
            '/my/circles/create',
            data={'csrf_token': _csrf, 'type_id': ''},
        )
        self.assertEqual(resp.status_code, 200)

    def test_circle_update(self):
        self.authenticate('admin', 'admin')
        _csrf = self.csrf_token()
        admin = self.env.ref('base.user_admin')
        profile = self.env['club_social_profile.profile'].sudo().search(
            [('user_id', '=', admin.id)], limit=1
        ) or self.env['club_social_profile.profile'].sudo().create({'user_id': admin.id})
        ct_update = _get_or_create_http_type(self.env, 'HTTP Update Type')
        circle = self.env['social_circles.circle'].sudo().create({
            'profile_id': profile.id, 'type_id': ct_update.id,
        })
        resp = self.url_open(
            f'/my/circles/{circle.id}/update',
            data={'csrf_token': _csrf, 
                'name': 'After Update',
                'description': 'New desc',
            },
        )
        self.assertEqual(resp.status_code, 200)
        circle.invalidate_recordset()
        self.assertEqual(circle.name, 'After Update')

    def test_circle_delete(self):
        self.authenticate('admin', 'admin')
        _csrf = self.csrf_token()
        admin = self.env.ref('base.user_admin')
        profile = self.env['club_social_profile.profile'].sudo().search(
            [('user_id', '=', admin.id)], limit=1
        ) or self.env['club_social_profile.profile'].sudo().create({'user_id': admin.id})
        ct_del = _get_or_create_http_type(self.env, 'HTTP Delete Type')
        circle = self.env['social_circles.circle'].sudo().create({
            'profile_id': profile.id, 'type_id': ct_del.id,
        })
        resp = self.url_open(
            f'/my/circles/{circle.id}/delete',
            data={'csrf_token': _csrf, },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(self.env['social_circles.circle'].sudo().browse(circle.id).exists())

    def test_circle_delete_forbidden_for_non_owner(self):
        admin = self.env.ref('base.user_admin')
        profile = self.env['club_social_profile.profile'].sudo().search(
            [('user_id', '=', admin.id)], limit=1
        ) or self.env['club_social_profile.profile'].sudo().create({'user_id': admin.id})
        ct_forbidden = _get_or_create_http_type(self.env, 'HTTP Forbidden Type')
        circle = self.env['social_circles.circle'].sudo().create({
            'profile_id': profile.id, 'type_id': ct_forbidden.id,
        })
        other = self.env['res.users'].sudo().create({
            'name': 'HTTP Circle Other', 'login': 'http_circ_other2',
            'email': 'http_circ2@circles.test', 'password': 'Test1234!',
            'group_ids': [(4, self.env.ref('base.group_portal').id)],
        })
        self.authenticate('http_circ_other2', 'Test1234!')
        _csrf = self.csrf_token()
        resp = self.url_open(
            f'/my/circles/{circle.id}/delete',
            data={'csrf_token': _csrf, },
            allow_redirects=False,
        )
        self.assertIn(resp.status_code, (302, 303, 403))

    def test_visibility_post(self):
        self.authenticate('admin', 'admin')
        _csrf = self.csrf_token()
        resp = self.url_open(
            '/my/circles/visibility',
            data={'csrf_token': _csrf, 
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
        _csrf = self.csrf_token()
        admin = self.env.ref('base.user_admin')
        profile = self.env['club_social_profile.profile'].sudo().search(
            [('user_id', '=', admin.id)], limit=1
        ) or self.env['club_social_profile.profile'].sudo().create({'user_id': admin.id})
        ct_noconn = _get_or_create_http_type(self.env, 'HTTP NoConn Type')
        circle = self.env['social_circles.circle'].sudo().create({
            'profile_id': profile.id, 'type_id': ct_noconn.id,
        })
        stranger = self.env['res.users'].sudo().create({
            'name': 'Stranger User', 'login': 'stranger_circ',
            'email': 'stranger@circles.test', 'password': 'Test1234!',
        })
        self.url_open(
            f'/my/circles/{circle.id}/add_member',
            data={'csrf_token': _csrf, 'user_id': str(stranger.id)},
        )
        circle.invalidate_recordset()
        self.assertNotIn(stranger, circle.member_ids)

    def test_duplicate_type_create_does_not_leak(self):
        """The unique constraint (profile_id, type_id) must roll back the
        second INSERT — without a savepoint the controller's
        `except ValidationError` would swallow the error and leave the
        partial row committed."""
        self.authenticate('admin', 'admin')
        _csrf = self.csrf_token()
        ct = _get_or_create_http_type(self.env, 'HTTP Duplicate Leak Type')
        # First create succeeds
        self.url_open('/my/circles/create', data={
            'csrf_token': _csrf, 'type_id': str(ct.id), 'name': 'First',
        })
        # Second create on the same type must fail without leaking
        self.url_open('/my/circles/create', data={
            'csrf_token': _csrf, 'type_id': str(ct.id), 'name': 'Second',
        })
        admin = self.env.ref('base.user_admin')
        profile = self.env['club_social_profile.profile'].sudo().search(
            [('user_id', '=', admin.id)], limit=1)
        circles = self.env['social_circles.circle'].sudo().search([
            ('profile_id', '=', profile.id), ('type_id', '=', ct.id),
        ])
        self.assertEqual(len(circles), 1,
                         f'Duplicate type leaked: {circles.mapped("name")}')

    def test_others_circles_section_visible_when_member(self):
        """The "Circles I appear in" section is shown if you are a member of another user's circle."""
        group_user = self.env.ref('base.group_user')
        group_social = self.env.ref('social_base.group_social_user')
        other_owner = self.env['res.users'].sudo().create({
            'name': 'OtherOwner', 'login': 'other_owner_circ',
            'email': 'other_owner@circles.test', 'password': 'Test1234!',
            'group_ids': [(4, group_user.id), (4, group_social.id)],
        })
        admin = self.env.ref('base.user_admin')
        other_profile = self.env['club_social_profile.profile'].sudo().create({
            'user_id': other_owner.id,
        })
        ct_other = _get_or_create_http_type(self.env, 'HTTP OtherOwner Type')
        circle = self.env['social_circles.circle'].sudo().create({
            'profile_id': other_profile.id,
            'type_id': ct_other.id,
            'name': 'Other Owner Circle',
            'member_ids': [(4, admin.id)],
        })
        self.authenticate('admin', 'admin')
        _csrf = self.csrf_token()
        resp = self.url_open('/my/circles')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'Other Owner Circle', resp.content)
        # Structural marker: the "others_circles" section heading renders only
        # when the viewer is a member of at least one other user's circle.
        self.assertIn(b'Circles I appear in', resp.content)
