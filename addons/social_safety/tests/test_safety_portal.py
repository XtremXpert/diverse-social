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


@tagged('social_safety', 'safety_portal', 'post_install', '-at_install')
class TestSafetyPortalHttp(HttpCase):

    def test_safety_unauthenticated_redirects(self):
        resp = self.url_open('/safety', allow_redirects=False)
        self.assertIn(resp.status_code, (302, 303))

    def test_safety_authenticated_ok(self):
        self.authenticate('admin', 'admin')
        resp = self.url_open('/safety')
        self.assertEqual(resp.status_code, 200)

    def test_safety_page_shows_sections(self):
        self.authenticate('admin', 'admin')
        resp = self.url_open('/safety')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'Mode discret', resp.content)
        self.assertIn(b'Sortie rapide', resp.content)
        self.assertIn(b'bloqués', resp.content)

    def test_panic_activate_redirects(self):
        self.authenticate('admin', 'admin')
        resp = self.url_open(
            '/safety/panic/activate',
            data={'csrf_token': self.csrf_token()},
            allow_redirects=False,
        )
        self.assertIn(resp.status_code, (302, 303))

    def test_panic_lift_redirects(self):
        self.authenticate('admin', 'admin')
        resp = self.url_open(
            '/safety/panic/lift',
            data={'csrf_token': self.csrf_token()},
            allow_redirects=False,
        )
        self.assertIn(resp.status_code, (302, 303))

    def test_safety_page_has_quick_exit_info(self):
        self.authenticate('admin', 'admin')
        resp = self.url_open('/safety')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('Échap'.encode(), resp.content)
