from datetime import date

from odoo.tests import HttpCase, TransactionCase, tagged
from odoo.exceptions import ValidationError


def _make_member(env, name, login, **profile_vals):
    group_user = env.ref('base.group_user')
    group_social = env.ref('social_base.group_social_user')
    user = env['res.users'].create({
        'name': name, 'login': login, 'email': f'{login}@age.test',
        'password': 'Test1234!',
        'group_ids': [(4, group_user.id), (4, group_social.id)],
    })
    profile = env['club_social_profile.profile'].sudo().get_or_create_for_user(user)
    if profile_vals:
        profile.sudo().write(profile_vals)
    return user, profile


@tagged('social_age_gate')
class TestAgeGateModel(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.today_year = date.today().year

    def test_age_gate_passed_default_false(self):
        _, profile = _make_member(self.env, 'Adult1', 'adult1')
        self.assertFalse(profile.age_gate_passed)

    def test_create_with_adult_birth_year_does_not_auto_gate(self):
        # Consent is explicit: declaring an adult birth_year alone must NOT
        # set age_gate_passed — only /age-verify or the onboarding wizard does.
        _, profile = _make_member(
            self.env, 'Adult2', 'adult2',
            birth_year=self.today_year - 25,
        )
        self.assertFalse(profile.age_gate_passed)

    def test_create_with_minor_birth_year_raises(self):
        # ValidationError comes from club_social_profile._check_birth_year_adult.
        group_user = self.env.ref('base.group_user')
        group_social = self.env.ref('social_base.group_social_user')
        user = self.env['res.users'].create({
            'name': 'Minor', 'login': 'minor_test',
            'email': 'minor@age.test', 'password': 'Test1234!',
            'group_ids': [(4, group_user.id), (4, group_social.id)],
        })
        profile = self.env['club_social_profile.profile'].sudo().get_or_create_for_user(user)
        with self.assertRaises(ValidationError):
            profile.sudo().write({'birth_year': self.today_year - 10})

    def test_write_birth_year_adult_does_not_set_gate(self):
        _, profile = _make_member(self.env, 'Adult3', 'adult3')
        self.assertFalse(profile.age_gate_passed)
        profile.sudo().write({'birth_year': self.today_year - 30})
        self.assertFalse(profile.age_gate_passed)

    def test_explicit_gate_persists_after_unrelated_write(self):
        _, profile = _make_member(
            self.env, 'Adult5', 'adult5',
            birth_year=self.today_year - 30,
        )
        # Simulate explicit consent (portal/wizard sets it directly).
        profile.sudo().write({'age_gate_passed': True})
        profile.sudo().write({'city': 'Montréal'})
        self.assertTrue(profile.age_gate_passed)

    def test_post_init_hook_migrates_existing_adults(self):
        _, profile = _make_member(
            self.env, 'Adult6', 'adult6',
            birth_year=self.today_year - 40,
        )
        # Force reset to simulate pre-install state
        # flush=False to avoid re-writing the ORM-cached True before clearing the cache
        self.env.cr.execute(
            "UPDATE club_social_profile_profile SET age_gate_passed = FALSE WHERE id = %s",
            (profile.id,),
        )
        profile.invalidate_recordset(['age_gate_passed'], flush=False)
        self.assertFalse(profile.age_gate_passed)

        from odoo.addons.social_age_gate import post_init_hook
        post_init_hook(self.env)

        profile.invalidate_recordset(['age_gate_passed'])
        self.assertTrue(profile.age_gate_passed)

    def test_post_init_hook_skips_no_birth_year(self):
        _, profile = _make_member(self.env, 'Anon7', 'anon7')
        self.assertFalse(profile.age_gate_passed)

        from odoo.addons.social_age_gate import post_init_hook
        post_init_hook(self.env)

        self.assertFalse(profile.age_gate_passed)

    def test_batch_create_never_auto_gates(self):
        """Batch create with adult birth_year: age_gate_passed stays False
        everywhere (consent must always be given explicitly)."""
        group_user = self.env.ref('base.group_user')
        group_social = self.env.ref('social_base.group_social_user')
        u1 = self.env['res.users'].create({
            'name': 'BatchAdult', 'login': 'batch_adult', 'email': 'batch_adult@age.test',
            'group_ids': [(4, group_user.id), (4, group_social.id)],
        })
        u2 = self.env['res.users'].create({
            'name': 'BatchAnon', 'login': 'batch_anon', 'email': 'batch_anon@age.test',
            'group_ids': [(4, group_user.id), (4, group_social.id)],
        })
        profiles = self.env['club_social_profile.profile'].sudo().create([
            {'user_id': u1.id, 'birth_year': self.today_year - 25},
            {'user_id': u2.id},
        ])
        self.assertFalse(profiles[0].age_gate_passed)
        self.assertFalse(profiles[1].age_gate_passed)

    def test_write_birth_year_does_not_reset_explicit_gate(self):
        """Writing birth_year on an already-gated profile (via explicit consent)
        does not reset it."""
        _, profile = _make_member(
            self.env, 'Adult8', 'adult8',
            birth_year=self.today_year - 30,
        )
        profile.sudo().write({'age_gate_passed': True})
        profile.sudo().write({'birth_year': self.today_year - 35})
        self.assertTrue(profile.age_gate_passed)


@tagged('social_age_gate', 'post_install', '-at_install')
class TestAgeGateHttp(HttpCase):

    def _setup_user(self, login, birth_year=None, gate_passed=False):
        group_user = self.env.ref('base.group_user')
        group_social = self.env.ref('social_base.group_social_user')
        user = self.env['res.users'].create({
            'name': login.capitalize(), 'login': login,
            'email': f'{login}@age.test', 'password': 'Test1234!',
            'group_ids': [(4, group_user.id), (4, group_social.id)],
        })
        profile = self.env['club_social_profile.profile'].sudo().get_or_create_for_user(user)
        vals = {'age_gate_passed': gate_passed}
        if birth_year:
            vals['birth_year'] = birth_year
        profile.sudo().write(vals)
        return user, profile

    def test_age_verify_unauthenticated_redirects(self):
        resp = self.url_open('/age-verify', allow_redirects=False)
        self.assertIn(resp.status_code, (302, 303))

    def test_age_verify_gated_user_sees_form(self):
        user, _ = self._setup_user('gated1', gate_passed=False)
        self.authenticate(user.login, 'Test1234!')
        resp = self.url_open('/age-verify')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'18 and over', resp.content)

    def test_age_verify_passed_user_redirected(self):
        user, _ = self._setup_user('passed1', gate_passed=True)
        self.authenticate(user.login, 'Test1234!')
        resp = self.url_open('/age-verify', allow_redirects=False)
        self.assertIn(resp.status_code, (302, 303))
        self.assertIn('/web', resp.headers.get('Location', ''))

    def test_home_redirects_gated_user_to_age_verify(self):
        user, _ = self._setup_user('gated2', gate_passed=False)
        self.authenticate(user.login, 'Test1234!')
        resp = self.url_open('/my/home', allow_redirects=False)
        self.assertIn(resp.status_code, (302, 303))
        self.assertIn('/age-verify', resp.headers.get('Location', ''))

    def test_submit_no_checkbox_shows_error(self):
        user, _ = self._setup_user('gated3', gate_passed=False)
        self.authenticate(user.login, 'Test1234!')
        _csrf = self.csrf_token()
        resp = self.url_open('/age-verify/submit', data={
            'csrf_token': _csrf, 'birth_year': '1990',
        })
        self.assertEqual(resp.status_code, 200)
        # Structural marker: the age-gate error container is rendered.
        self.assertIn(b'age-gate-error', resp.content)

    def test_submit_minor_birth_year_shows_error(self):
        today_year = date.today().year
        user, _ = self._setup_user('gated4', gate_passed=False)
        self.authenticate(user.login, 'Test1234!')
        _csrf = self.csrf_token()
        resp = self.url_open('/age-verify/submit', data={
            'csrf_token': _csrf,
            'birth_year': str(today_year - 10),
            'confirmed': '1',
        })
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'age-gate-error', resp.content)

    def test_submit_valid_sets_gate_and_redirects(self):
        user, profile = self._setup_user('gated5', gate_passed=False)
        profile.sudo().write({'onboarding_done': True})
        self.authenticate(user.login, 'Test1234!')
        _csrf = self.csrf_token()
        resp = self.url_open('/age-verify/submit', data={
            'csrf_token': _csrf,
            'birth_year': '1990',
            'confirmed': '1',
        }, allow_redirects=False)
        self.assertIn(resp.status_code, (302, 303))
        self.assertIn('/web', resp.headers.get('Location', ''))
        profile.invalidate_recordset(['age_gate_passed'])
        self.assertTrue(profile.age_gate_passed)

    def test_submit_without_birth_year_also_sets_gate(self):
        user, profile = self._setup_user('gated6', gate_passed=False)
        profile.sudo().write({'onboarding_done': True})
        self.authenticate(user.login, 'Test1234!')
        _csrf = self.csrf_token()
        resp = self.url_open('/age-verify/submit', data={
            'csrf_token': _csrf,
            'confirmed': '1',
        }, allow_redirects=False)
        self.assertIn(resp.status_code, (302, 303))
        profile.invalidate_recordset(['age_gate_passed'])
        self.assertTrue(profile.age_gate_passed)

    def test_submit_birth_year_before_1900_shows_error(self):
        user, _ = self._setup_user('gated8', gate_passed=False)
        self.authenticate(user.login, 'Test1234!')
        _csrf = self.csrf_token()
        resp = self.url_open('/age-verify/submit', data={
            'csrf_token': _csrf,
            'birth_year': '1800',
            'confirmed': '1',
        })
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'age-gate-error', resp.content)

    def test_submit_already_gated_redirects_to_web(self):
        user, _ = self._setup_user('gated9', gate_passed=True)
        self.authenticate(user.login, 'Test1234!')
        _csrf = self.csrf_token()
        resp = self.url_open('/age-verify/submit', data={
            'csrf_token': _csrf,
            'confirmed': '1',
        }, allow_redirects=False)
        self.assertIn(resp.status_code, (302, 303))
        self.assertIn('/web', resp.headers.get('Location', ''))

    def test_submit_redirects_to_onboarding_if_not_done(self):
        user, profile = self._setup_user('gated7', gate_passed=False)
        profile.sudo().write({'onboarding_done': False})
        self.authenticate(user.login, 'Test1234!')
        _csrf = self.csrf_token()
        resp = self.url_open('/age-verify/submit', data={
            'csrf_token': _csrf,
            'confirmed': '1',
        }, allow_redirects=False)
        self.assertIn(resp.status_code, (302, 303))
        self.assertIn('/onboarding', resp.headers.get('Location', ''))
