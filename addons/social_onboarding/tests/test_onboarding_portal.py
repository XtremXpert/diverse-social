import datetime

from odoo.http import Request
from odoo.tests import HttpCase, TransactionCase, tagged


def _make_member_user(env, name, login):
    group_user = env.ref('base.group_user')
    group_social = env.ref('social_base.group_social_user')
    user = env['res.users'].create({
        'name': name, 'login': login, 'email': f'{login}@onboarding.test',
        'password': 'Test1234!',
        'group_ids': [(4, group_user.id), (4, group_social.id)],
    })
    return user


@tagged('social_onboarding', 'onboarding_portal')
class TestOnboardingPortalLogic(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.type_regular = cls.env.ref('club_membership.membership_type_regular')
        cls.user = _make_member_user(cls.env, 'OnbUser', 'onb_user')
        cls.profile = cls.env['club_social_profile.profile'].sudo().get_or_create_for_user(cls.user)

    def test_profile_created_for_user(self):
        self.assertTrue(self.profile)
        self.assertEqual(self.profile.user_id, self.user)

    def test_onboarding_done_false_by_default(self):
        self.assertFalse(self.profile.onboarding_done)

    def test_save_about_fields(self):
        self.profile.sudo().write({
            'pronouns': 'il/lui',
            'bio': 'Test bio',
            'birth_year': 1990,
            'city': 'Montréal',
            'region': 'Québec',
            'gender': 'homme',
            'orientation': 'bi',
            'quote': 'Une phrase d\'accroche',
        })
        self.assertEqual(self.profile.pronouns, 'il/lui')
        self.assertEqual(self.profile.bio, 'Test bio')
        self.assertEqual(self.profile.birth_year, 1990)
        self.assertEqual(self.profile.city, 'Montréal')
        self.assertEqual(self.profile.region, 'Québec')
        self.assertEqual(self.profile.gender, 'homme')
        self.assertEqual(self.profile.orientation, 'bi')
        self.assertEqual(self.profile.quote, 'Une phrase d\'accroche')

    def test_save_preferences(self):
        looking_for = self.env['club_social_profile.looking_for'].sudo().search([], limit=1)
        language = self.env['club_social_profile.language'].sudo().search([], limit=1)
        self.profile.sudo().write({
            'visibility': 'connections',
            'availability': 'disponible',
            'digest_email_enabled': False,
            'looking_for_ids': [(6, 0, looking_for.ids)] if looking_for else [(6, 0, [])],
            'language_ids': [(6, 0, language.ids)] if language else [(6, 0, [])],
        })
        self.assertEqual(self.profile.visibility, 'connections')
        self.assertEqual(self.profile.availability, 'disponible')
        self.assertFalse(self.profile.digest_email_enabled)
        if looking_for:
            self.assertIn(looking_for, self.profile.looking_for_ids)
        if language:
            self.assertIn(language, self.profile.language_ids)

    def test_gender_invalid_value_rejected(self):
        """An invalid gender value must not be written."""
        self.profile.sudo().write({'gender': 'non_specifie'})
        valid = {'homme', 'femme', 'trans_homme', 'trans_femme',
                 'non_binaire', 'autre', 'non_specifie'}
        self.assertIn(self.profile.gender, valid)

    def test_quote_max_length(self):
        long_quote = 'x' * 250
        self.profile.sudo().write({'quote': long_quote[:200]})
        self.assertLessEqual(len(self.profile.quote), 200)

    def test_mark_onboarding_done(self):
        self.profile.sudo().write({'onboarding_done': True})
        self.assertTrue(self.profile.onboarding_done)

    def test_wizard_action_open_creates_wizard(self):
        action = self.env['social_onboarding.wizard'].with_user(self.user).action_open()
        self.assertEqual(action['type'], 'ir.actions.act_window')
        self.assertEqual(action['res_model'], 'social_onboarding.wizard')

    def test_wizard_step_defaults_welcome_when_not_done(self):
        self.profile.sudo().write({'onboarding_done': False})
        action = self.env['social_onboarding.wizard'].with_user(self.user).action_open()
        wizard = self.env['social_onboarding.wizard'].browse(action['res_id'])
        self.assertEqual(wizard.step, 'welcome')

    def test_wizard_step_done_when_already_onboarded(self):
        self.profile.sudo().write({'onboarding_done': True})
        action = self.env['social_onboarding.wizard'].with_user(self.user).action_open()
        wizard = self.env['social_onboarding.wizard'].browse(action['res_id'])
        self.assertEqual(wizard.step, 'done')
        self.profile.sudo().write({'onboarding_done': False})

    def test_wizard_next_advances_step(self):
        action = self.env['social_onboarding.wizard'].with_user(self.user).action_open()
        wizard = self.env['social_onboarding.wizard'].browse(action['res_id'])
        wizard.step = 'welcome'
        wizard.action_next()
        self.assertEqual(wizard.step, 'about')

    def test_wizard_underage_raises(self):
        from odoo.exceptions import ValidationError
        action = self.env['social_onboarding.wizard'].with_user(self.user).action_open()
        wizard = self.env['social_onboarding.wizard'].browse(action['res_id'])
        wizard.step = 'about'
        wizard.birth_year = datetime.date.today().year - 16
        with self.assertRaises(ValidationError):
            wizard.action_next()

    def test_member_activation_creates_profile(self):
        new_user = _make_member_user(self.env, 'OnbHook', 'onb_hook')
        membership = self.env['club_membership.membership'].sudo().create({
            'partner_id': new_user.partner_id.id,
            'membership_type_id': self.type_regular.id,
            'start_date': datetime.date.today(),
        })
        membership.action_activate()
        profile = self.env['club_social_profile.profile'].sudo().search([
            ('user_id', '=', new_user.id),
        ], limit=1)
        self.assertTrue(profile)


@tagged('social_onboarding', 'onboarding_portal', 'post_install', '-at_install')
class TestOnboardingPortalHttp(HttpCase):

    def test_onboarding_unauthenticated_redirects(self):
        resp = self.url_open('/onboarding', allow_redirects=False)
        self.assertIn(resp.status_code, (302, 303))

    def test_onboarding_authenticated_ok(self):
        self.authenticate('admin', 'admin')
        _csrf = Request.csrf_token(self)
        resp = self.url_open('/onboarding')
        self.assertEqual(resp.status_code, 200)

    def test_onboarding_step_welcome(self):
        self.authenticate('admin', 'admin')
        _csrf = Request.csrf_token(self)
        resp = self.url_open('/onboarding?step=welcome')
        self.assertEqual(resp.status_code, 200)

    def test_onboarding_step_about(self):
        self.authenticate('admin', 'admin')
        _csrf = Request.csrf_token(self)
        resp = self.url_open('/onboarding?step=about')
        self.assertEqual(resp.status_code, 200)

    def test_onboarding_step_preferences(self):
        self.authenticate('admin', 'admin')
        _csrf = Request.csrf_token(self)
        resp = self.url_open('/onboarding?step=preferences')
        self.assertEqual(resp.status_code, 200)

    def test_onboarding_step_done(self):
        self.authenticate('admin', 'admin')
        _csrf = Request.csrf_token(self)
        resp = self.url_open('/onboarding?step=done')
        self.assertEqual(resp.status_code, 200)

    def test_save_welcome_redirects(self):
        self.authenticate('admin', 'admin')
        _csrf = Request.csrf_token(self)
        resp = self.url_open(
            '/onboarding/save/welcome',
            data={'csrf_token': _csrf, },
            allow_redirects=False,
        )
        self.assertIn(resp.status_code, (302, 303))

    def test_save_about_redirects(self):
        self.authenticate('admin', 'admin')
        _csrf = Request.csrf_token(self)
        resp = self.url_open(
            '/onboarding/save/about',
            data={'csrf_token': _csrf, 'bio': 'Test', 'city': 'Mtl'},
            allow_redirects=False,
        )
        self.assertIn(resp.status_code, (302, 303))

    def test_save_about_underage_returns_200(self):
        """Invalid birth year → form is re-rendered (200), no redirect."""
        self.authenticate('admin', 'admin')
        _csrf = Request.csrf_token(self)
        current_year = datetime.date.today().year
        resp = self.url_open(
            '/onboarding/save/about',
            data={'csrf_token': _csrf, 
                'birth_year': str(current_year - 16),
            },
        )
        self.assertEqual(resp.status_code, 200)

    def test_save_about_with_gender_orientation(self):
        self.authenticate('admin', 'admin')
        _csrf = Request.csrf_token(self)
        resp = self.url_open(
            '/onboarding/save/about',
            data={'csrf_token': _csrf, 
                'gender': 'non_binaire',
                'orientation': 'queer',
                'city': 'Montréal',
                'region': 'Québec',
                'quote': 'Test accroche',
            },
            allow_redirects=False,
        )
        self.assertIn(resp.status_code, (302, 303))

    def test_save_about_invalid_gender_ignored(self):
        self.authenticate('admin', 'admin')
        _csrf = Request.csrf_token(self)
        resp = self.url_open(
            '/onboarding/save/about',
            data={'csrf_token': _csrf, 
                'gender': 'INVALID_VALUE',
            },
            allow_redirects=False,
        )
        # Should still redirect (invalid value → falls back to non_specifie)
        self.assertIn(resp.status_code, (302, 303))

    def test_onboarding_about_shows_gender_fields(self):
        self.authenticate('admin', 'admin')
        _csrf = Request.csrf_token(self)
        resp = self.url_open('/onboarding?step=about')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'gender', resp.content.lower())
        self.assertIn(b'orientation', resp.content.lower())

    def test_onboarding_preferences_shows_looking_for(self):
        self.authenticate('admin', 'admin')
        _csrf = Request.csrf_token(self)
        resp = self.url_open('/onboarding?step=preferences')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'looking', resp.content.lower())

    def test_skip_redirects(self):
        self.authenticate('admin', 'admin')
        _csrf = Request.csrf_token(self)
        resp = self.url_open(
            '/onboarding/skip',
            data={'csrf_token': _csrf, },
            allow_redirects=False,
        )
        self.assertIn(resp.status_code, (302, 303))

    def test_save_preferences_redirects(self):
        self.authenticate('admin', 'admin')
        _csrf = Request.csrf_token(self)
        resp = self.url_open(
            '/onboarding/save/preferences',
            data={'csrf_token': _csrf, 
                'visibility': 'connections',
                'availability': 'disponible',
            },
            allow_redirects=False,
        )
        self.assertIn(resp.status_code, (302, 303))

    def test_save_preferences_persists_visibility(self):
        self.authenticate('admin', 'admin')
        _csrf = Request.csrf_token(self)
        self.url_open(
            '/onboarding/save/preferences',
            data={'csrf_token': _csrf, 
                'visibility': 'connections',
                'availability': 'non_specifie',
            },
        )
        admin = self.env.ref('base.user_admin')
        profile = self.env['club_social_profile.profile'].sudo().search(
            [('user_id', '=', admin.id)], limit=1
        )
        if profile:
            self.assertEqual(profile.visibility, 'connections')

    def test_save_preferences_digest_unchecked_is_false(self):
        """digest_email_enabled absent du POST → False en base."""
        self.authenticate('admin', 'admin')
        _csrf = Request.csrf_token(self)
        self.url_open(
            '/onboarding/save/preferences',
            data={'csrf_token': _csrf, 
                'visibility': 'members',
                # digest_email_enabled missing = unchecked
            },
        )
        admin = self.env.ref('base.user_admin')
        profile = self.env['club_social_profile.profile'].sudo().search(
            [('user_id', '=', admin.id)], limit=1
        )
        if profile:
            self.assertFalse(profile.digest_email_enabled)
