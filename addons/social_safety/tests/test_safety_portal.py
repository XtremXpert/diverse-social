from odoo.http import Request
from odoo.tests import HttpCase, TransactionCase, tagged
from odoo.exceptions import UserError


def _make_social_user(env, name, login):
    group_social = env.ref('social_base.group_social_user')
    return env['res.users'].create({
        'name': name, 'login': login, 'email': f'{login}@safety.test',
        'password': 'Test1234!',
        'group_ids': [(4, group_social.id)],
    })


@tagged('social_safety', 'safety_portal')
class TestSafetyPortalData(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = _make_social_user(cls.env, 'SafetyUser', 'safety_user')
        cls.other = _make_social_user(cls.env, 'SafetyOther', 'safety_other')
        cls.profile = cls.env['club_social_profile.profile'].sudo().get_or_create_for_user(cls.user)
        cls.profile.sudo().write({'visibility': 'members', 'onboarding_done': True})

    # ── Panic mode ────────────────────────────────────────────────────────────

    def test_panic_activate_hides_profile(self):
        self.profile.sudo().with_user(self.user).action_panic()
        self.assertTrue(self.profile.panic_mode)
        self.assertEqual(self.profile.visibility, 'connections')
        self.assertTrue(self.profile.panic_activated_at)

    def test_panic_lift_restores_visibility(self):
        self.profile.sudo().write({'visibility': 'members'})
        self.profile.sudo().with_user(self.user).action_panic()
        self.assertEqual(self.profile.visibility, 'connections')
        self.profile.sudo().with_user(self.user).action_panic_lift()
        self.assertFalse(self.profile.panic_mode)
        self.assertEqual(self.profile.visibility, 'members')
        self.assertFalse(self.profile.panic_activated_at)

    def test_panic_idempotent(self):
        self.profile.sudo().with_user(self.user).action_panic()
        activated_at = self.profile.panic_activated_at
        self.profile.sudo().with_user(self.user).action_panic()
        self.assertEqual(self.profile.panic_activated_at, activated_at)
        self.profile.sudo().with_user(self.user).action_panic_lift()

    def test_panic_other_user_raises(self):
        with self.assertRaises(UserError):
            self.profile.sudo().with_user(self.other).action_panic()

    def test_panic_lift_other_user_raises(self):
        self.profile.sudo().with_user(self.user).action_panic()
        with self.assertRaises(UserError):
            self.profile.sudo().with_user(self.other).action_panic_lift()
        self.profile.sudo().with_user(self.user).action_panic_lift()

    def test_panic_mode_excluded_from_discovery(self):
        self.profile.sudo().with_user(self.user).action_panic()
        profiles = self.env['club_social_profile.profile'].sudo().search([
            ('visibility', '=', 'members'),
            ('panic_mode', '=', False),
            ('onboarding_done', '=', True),
        ])
        self.assertNotIn(self.profile.id, profiles.ids)
        self.profile.sudo().with_user(self.user).action_panic_lift()

    # ── Blocage ───────────────────────────────────────────────────────────────

    def test_block_prevents_contact(self):
        self.env['social_safety.block'].sudo().create({
            'blocker_id': self.user.id,
            'blocked_id': self.other.id,
        })
        other_profile = self.env['club_social_profile.profile'].sudo().get_or_create_for_user(
            self.other
        )
        safe = other_profile.is_safe_to_contact(self.user)
        self.assertFalse(safe)

    def test_unblock_restores_contact(self):
        block = self.env['social_safety.block'].sudo().create({
            'blocker_id': self.user.id,
            'blocked_id': self.other.id,
        })
        block.unlink()
        other_profile = self.env['club_social_profile.profile'].sudo().get_or_create_for_user(
            self.other
        )
        safe = other_profile.is_safe_to_contact(self.user)
        self.assertTrue(safe)

    def test_panic_saves_visibility(self):
        self.profile.sudo().write({'visibility': 'members'})
        self.profile.sudo().with_user(self.user).action_panic()
        self.assertEqual(self.profile.panic_saved_visibility, 'members')
        self.profile.sudo().with_user(self.user).action_panic_lift()


@tagged('social_safety', 'safety_portal', 'post_install', '-at_install')
class TestSafetyPortalHttp(HttpCase):

    def test_safety_unauthenticated_redirects(self):
        resp = self.url_open('/safety', allow_redirects=False)
        self.assertIn(resp.status_code, (302, 303))

    def test_safety_authenticated_ok(self):
        self.authenticate('admin', 'admin')
        _csrf = Request.csrf_token(self)
        resp = self.url_open('/safety')
        self.assertEqual(resp.status_code, 200)

    def test_safety_page_shows_sections(self):
        self.authenticate('admin', 'admin')
        _csrf = Request.csrf_token(self)
        resp = self.url_open('/safety')
        self.assertEqual(resp.status_code, 200)
        # Structural markers: the page renders the panic and quick-exit
        # form endpoints regardless of UI language.
        self.assertIn(b'/safety/panic/', resp.content)
        self.assertIn(b'Quick exit', resp.content)
        self.assertIn(b'social_safety.portal_safety_page', resp.content)

    def test_panic_activate_redirects(self):
        self.authenticate('admin', 'admin')
        _csrf = Request.csrf_token(self)
        resp = self.url_open(
            '/safety/panic/activate',
            data={'csrf_token': _csrf, },
            allow_redirects=False,
        )
        self.assertIn(resp.status_code, (302, 303))

    def test_panic_lift_redirects(self):
        self.authenticate('admin', 'admin')
        _csrf = Request.csrf_token(self)
        resp = self.url_open(
            '/safety/panic/lift',
            data={'csrf_token': _csrf, },
            allow_redirects=False,
        )
        self.assertIn(resp.status_code, (302, 303))

    def test_safety_page_has_quick_exit_info(self):
        self.authenticate('admin', 'admin')
        _csrf = Request.csrf_token(self)
        resp = self.url_open('/safety')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('Esc'.encode(), resp.content)

    def test_panic_activate_changes_db_state(self):
        group_social = self.env.ref('social_base.group_social_user')
        owner = self.env['res.users'].sudo().create({
            'name': 'Panic Owner', 'login': 'panic_owner_http',
            'email': 'panic@safety.test', 'password': 'Test1234!',
            'group_ids': [(4, group_social.id)],
        })
        profile = self.env['club_social_profile.profile'].sudo().get_or_create_for_user(owner)
        self.authenticate('panic_owner_http', 'Test1234!')
        _csrf = Request.csrf_token(self)
        self.url_open('/safety/panic/activate', data={'csrf_token': _csrf, })
        profile.invalidate_recordset()
        self.assertTrue(profile.panic_mode)

    def test_panic_lift_changes_db_state(self):
        group_social = self.env.ref('social_base.group_social_user')
        owner = self.env['res.users'].sudo().create({
            'name': 'Panic Lifter', 'login': 'panic_lifter_http',
            'email': 'lifter@safety.test', 'password': 'Test1234!',
            'group_ids': [(4, group_social.id)],
        })
        profile = self.env['club_social_profile.profile'].sudo().get_or_create_for_user(owner)
        profile.sudo().write({'panic_mode': True, 'panic_saved_visibility': 'members'})
        self.authenticate('panic_lifter_http', 'Test1234!')
        _csrf = Request.csrf_token(self)
        self.url_open('/safety/panic/lift', data={'csrf_token': _csrf, })
        profile.invalidate_recordset()
        self.assertFalse(profile.panic_mode)

    def test_remove_block_via_portal(self):
        group_social = self.env.ref('social_base.group_social_user')
        blocker = self.env['res.users'].sudo().create({
            'name': 'Block Remover', 'login': 'block_remover_http',
            'email': 'remover@safety.test', 'password': 'Test1234!',
            'group_ids': [(4, group_social.id)],
        })
        blocked = self.env['res.users'].sudo().create({
            'name': 'Blocked User', 'login': 'blocked_user_http',
            'email': 'blocked@safety.test', 'password': 'Test1234!',
        })
        block = self.env['social_safety.block'].sudo().create({
            'blocker_id': blocker.id, 'blocked_id': blocked.id,
        })
        self.authenticate('block_remover_http', 'Test1234!')
        _csrf = Request.csrf_token(self)
        resp = self.url_open(
            f'/safety/block/{block.id}/remove',
            data={'csrf_token': _csrf, },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(self.env['social_safety.block'].sudo().browse(block.id).exists())

    def test_remove_block_by_non_owner_ignored(self):
        """Un utilisateur ne peut pas supprimer le bloc d'un autre."""
        group_social = self.env.ref('social_base.group_social_user')
        blocker = self.env['res.users'].sudo().create({
            'name': 'Block Owner2', 'login': 'block_owner2_http',
            'email': 'owner2@safety.test', 'password': 'Test1234!',
        })
        blocked = self.env['res.users'].sudo().create({
            'name': 'Blocked2', 'login': 'blocked2_http',
            'email': 'blocked2@safety.test', 'password': 'Test1234!',
        })
        intruder = self.env['res.users'].sudo().create({
            'name': 'Intruder', 'login': 'intruder_block_http',
            'email': 'intruder@safety.test', 'password': 'Test1234!',
            'group_ids': [(4, group_social.id)],
        })
        block = self.env['social_safety.block'].sudo().create({
            'blocker_id': blocker.id, 'blocked_id': blocked.id,
        })
        self.authenticate('intruder_block_http', 'Test1234!')
        _csrf = Request.csrf_token(self)
        self.url_open(
            f'/safety/block/{block.id}/remove',
            data={'csrf_token': _csrf, },
        )
        self.assertTrue(self.env['social_safety.block'].sudo().browse(block.id).exists())

    def test_remove_mute_via_portal(self):
        group_social = self.env.ref('social_base.group_social_user')
        muter = self.env['res.users'].sudo().create({
            'name': 'Mute Remover', 'login': 'mute_remover_http',
            'email': 'mute_remover@safety.test', 'password': 'Test1234!',
            'group_ids': [(4, group_social.id)],
        })
        muted = self.env['res.users'].sudo().create({
            'name': 'Muted User', 'login': 'muted_user_http',
            'email': 'muted@safety.test', 'password': 'Test1234!',
        })
        mute = self.env['social_safety.mute'].sudo().create({
            'muter_id': muter.id, 'muted_id': muted.id,
        })
        self.authenticate('mute_remover_http', 'Test1234!')
        _csrf = Request.csrf_token(self)
        resp = self.url_open(
            f'/safety/mute/{mute.id}/remove',
            data={'csrf_token': _csrf, },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(self.env['social_safety.mute'].sudo().browse(mute.id).exists())
