import base64
import datetime
import json
import re
import time

from odoo import fields
from odoo.tests import HttpCase, new_test_user, tagged

from odoo.addons.auth_totp.models.totp import hotp
from odoo.addons.social_mobile.models.enrollment import PERIOD, totp
from odoo.addons.social_mobile.models.login import MAX_ATTEMPTS

API = '/api/social/v1'
TOTP_SECRET = 'IRXWM5LTIRXWM5LT'


def other(code):
    """Un code à 6 chiffres différent de ``code``."""
    return f'{(int(code) + 1) % 10 ** 6:06d}'


@tagged('post_install', '-at_install')
class TestLogin(HttpCase):
    """Connexion d'un compte existant : code par courriel ou mot de passe, double authentification."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.admin = cls.env.ref('base.user_admin')
        ICP = cls.env['ir.config_parameter'].sudo()
        ICP.set_int('base.login_cooldown_after', 0)  # les mauvais mots de passe des tests s'accumulent
        Policy = cls.env['social_privacy.policy.version'].sudo()
        Policy.search([]).write({'is_active': False})
        cls.policy = Policy.create({
            'name': "Politique de test", 'version_number': '9.9', 'language': 'fr',
            'content': '<p>Texte</p>', 'is_active': True,
        })
        cls.member = cls._make_user('membre.existant@example.com', sponsor=cls.admin)
        cls.orphan = cls._make_user('sans.parrain@example.com', sponsor=None)

    @classmethod
    def _make_user(cls, login, sponsor):
        user = new_test_user(cls.env, login=login, email=login, password='Mot-de-passe-1', groups='base.group_portal')
        cls.env['club_social_profile.profile'].sudo().get_or_create_for_user(user)
        if sponsor:
            cls.env['social_reputation.vouching'].with_user(sponsor).sudo().vouch_for(user)
        return user

    def call(self, path, body, headers=None, key=None):
        all_headers = {'Content-Type': 'application/json', **(headers or {})}
        if key:
            all_headers['Authorization'] = f'Bearer {key}'
        method = 'GET' if body is None else 'POST'
        return self.url_open(API + path, data=json.dumps(body) if body is not None else None,
                             headers=all_headers, method=method)

    def request_code(self, email):
        res = self.call('/login/code', {'email': email, 'device_name': 'iPhone', 'consent': True})
        self.assertEqual(res.status_code, 202, res.text)
        return res.json()

    def verify(self, challenge, code, secret=None):
        return self.call(f"/login/{challenge['login_id']}", {'code': code, 'consent': True, 'device_name': 'iPhone'},
                         headers={'X-Login-Secret': secret or challenge['login_secret']})

    def mails_to(self, email):
        return self.env['mail.mail'].sudo().search([('email_to', 'ilike', email)])

    def mailed_code(self, email):
        body = str(self.mails_to(email)[:1].body_html)
        return re.search(r'<b>(\d{6})</b>', body).group(1)

    def totp_now(self):
        return f'{hotp(base64.b32decode(TOTP_SECRET), int(time.time() // 30)):06d}'

    # ── Code par courriel ────────────────────────────────────────────────────

    def test_code_request_reveals_nothing(self):
        """Compte, compte sans parrain ou adresse inconnue : même réponse ; seul le titulaire
        d'un compte reçoit un courriel."""
        answers = [self.request_code(email) for email in
                   ('membre.existant@example.com', 'sans.parrain@example.com', 'inconnu@example.com')]
        self.assertEqual({tuple(sorted(a)) for a in answers}, {('expires_at', 'login_id', 'login_secret', 'state', 'step')})
        self.assertEqual({a['step'] for a in answers}, {'email'})
        self.assertRegex(str(self.mails_to('membre.existant@example.com').body_html), r'<b>\d{6}</b>')
        refusal = str(self.mails_to('sans.parrain@example.com').body_html)
        self.assertIn("pas de parrain", refusal)
        self.assertNotRegex(refusal, r'<b>\d{6}</b>')
        self.assertFalse(self.mails_to('inconnu@example.com'))

    def test_code_login(self):
        challenge = self.request_code('Membre.Existant@example.com')
        code = self.mailed_code('membre.existant@example.com')
        self.assertEqual(self.verify(challenge, other(code)).status_code, 401)
        res = self.verify(challenge, code)
        self.assertEqual(res.status_code, 200, res.text)
        payload = res.json()
        self.assertEqual((payload['state'], payload['user_id']), ('active', self.member.id))
        me = self.call('/me', None, key=payload['key'])
        self.assertEqual(me.status_code, 200, me.text)
        self.assertFalse(self.env['social_mobile.login'].sudo().search([('email', '=', 'membre.existant@example.com')]))
        # Le consentement à la politique en vigueur est enregistré.
        self.assertTrue(self.env['social_privacy.consent'].sudo().has_valid_consent(self.member))

    def test_code_attempts_and_secret(self):
        challenge = self.request_code('membre.existant@example.com')
        code = self.mailed_code('membre.existant@example.com')
        self.assertEqual(self.verify(challenge, code, secret='mauvais').status_code, 404)
        for _i in range(MAX_ATTEMPTS):
            self.assertEqual(self.verify(challenge, other(code)).status_code, 401)
        # Plus d'essai : même le bon code est refusé.
        self.assertEqual(self.verify(challenge, code).status_code, 404)

    def test_code_expires(self):
        challenge = self.request_code('membre.existant@example.com')
        login = self.env['social_mobile.login'].sudo().search([('uuid', '=', challenge['login_id'])])
        login.expires_at = fields.Datetime.now() - datetime.timedelta(seconds=1)
        self.assertEqual(self.verify(challenge, self.mailed_code('membre.existant@example.com')).status_code, 404)
        self.env['social_mobile.login']._cron_purge()
        self.assertFalse(login.exists())

    def test_unknown_email_code_fails_like_a_wrong_code(self):
        challenge = self.request_code('inconnu@example.com')
        self.assertEqual(self.verify(challenge, '123456').status_code, 401)

    def test_consent_required(self):
        res = self.call('/login/code', {'email': 'membre.existant@example.com'})
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()['error']['code'], 'consent_required')

    def test_login_differs_from_email(self):
        """Compte à l'identifiant libre : retrouvé par son adresse courriel, s'il est le seul."""
        user = new_test_user(self.env, login='pseudo-libre', email='Libre <libre@example.com>',
                             password='Mot-de-passe-1', groups='base.group_portal')
        self.env['social_reputation.vouching'].with_user(self.admin).sudo().vouch_for(user)
        challenge = self.request_code('libre@example.com')
        res = self.verify(challenge, self.mailed_code('libre@example.com'))
        self.assertEqual((res.status_code, res.json().get('user_id')), (200, user.id), res.text)
        res = self.password('libre@example.com', 'Mot-de-passe-1')
        self.assertEqual((res.status_code, res.json().get('user_id')), (200, user.id), res.text)
        # Deux comptes avec la même adresse : aucun n'est choisi.
        new_test_user(self.env, login='autre-libre', email='libre@example.com', groups='base.group_portal')
        self.assertEqual(self.password('libre@example.com', 'Mot-de-passe-1').status_code, 401)

    # ── Mot de passe ─────────────────────────────────────────────────────────

    def password(self, email, password):
        return self.call('/login/password', {'email': email, 'password': password, 'device_name': 'iPhone', 'consent': True})

    def test_password_login(self):
        res = self.password('membre.existant@example.com', 'Mot-de-passe-1')
        self.assertEqual(res.status_code, 200, res.text)
        self.assertEqual(res.json()['user_id'], self.member.id)

    def test_password_failures_look_alike(self):
        wrong = self.password('membre.existant@example.com', 'faux')
        unknown = self.password('inconnu@example.com', 'Mot-de-passe-1')
        self.assertEqual((wrong.status_code, unknown.status_code), (401, 401))
        self.assertEqual(wrong.json(), unknown.json())

    def test_api_key_is_not_a_password(self):
        key = self.env['res.users.apikeys'].with_user(self.member).sudo()._generate('rpc', 'test', None)
        self.assertEqual(self.password('membre.existant@example.com', key).status_code, 401)

    def test_refusals_after_identity(self):
        res = self.password('sans.parrain@example.com', 'Mot-de-passe-1')
        self.assertEqual(res.status_code, 403)
        self.assertIn("administrateur", res.json()['error']['message'])
        profile = self.env['club_social_profile.profile'].sudo().search([('user_id', '=', self.member.id)])
        profile.is_banned = True
        res = self.password('membre.existant@example.com', 'Mot-de-passe-1')
        self.assertEqual(res.status_code, 403)
        self.assertIn("suspendu", res.json()['error']['message'])

    def test_qr_refusal_points_to_existing_account(self):
        res = self.call('/enroll', {'email': 'membre.existant@example.com', 'consent': True})
        enrollment = res.json()
        step = int(fields.Datetime.now().timestamp() // PERIOD)
        key, _exp = self.env['res.users.apikeys'].with_user(self.admin)._social_mobile_generate('test')
        res = self.call('/sponsor/confirm', {'enrollment_id': enrollment['enrollment_id'],
                                             'code': totp(enrollment['qr_secret'], step)}, key=key)
        self.assertEqual(res.status_code, 409)
        self.assertIn("J'ai déjà un compte", res.json()['error']['message'])

    # ── Double authentification ──────────────────────────────────────────────

    def test_totp_required_on_both_paths(self):
        self.member.sudo().totp_secret = TOTP_SECRET
        self.assertEqual(self.member._mfa_type(), 'totp')

        # Mot de passe → code de l'application d'authentification.
        res = self.password('membre.existant@example.com', 'Mot-de-passe-1')
        self.assertEqual(res.status_code, 202, res.text)
        challenge = res.json()
        self.assertEqual(challenge['step'], 'totp')
        self.assertEqual(self.verify(challenge, other(self.totp_now())).status_code, 401)
        res = self.verify(challenge, self.totp_now())
        self.assertEqual(res.status_code, 200, res.text)

        # Code par courriel → le courriel ne suffit pas.
        self.member.sudo().totp_last_counter = 0
        challenge = self.request_code('membre.existant@example.com')
        res = self.verify(challenge, self.mailed_code('membre.existant@example.com'))
        self.assertEqual(res.status_code, 202, res.text)
        self.assertEqual(res.json()['step'], 'totp')
        res = self.verify(challenge, self.totp_now())
        self.assertEqual(res.status_code, 200, res.text)
