import json

from odoo import fields
from odoo.tests import HttpCase, new_test_user, tagged

from odoo.addons.social_mobile.models.enrollment import PERIOD, totp

API = '/api/social/v1'


@tagged('post_install', '-at_install')
class TestEnrollment(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.admin = cls.env.ref('base.user_admin')
        Policy = cls.env['social_privacy.policy.version'].sudo()
        Policy.search([]).write({'is_active': False})
        cls.policy = Policy.create({
            'name': "Politique de test", 'version_number': '9.9', 'language': 'fr',
            'content': '<p>Texte</p>', 'is_active': True,
        })
        cls.sponsor = cls._make_member('sponsor.mobile@example.com', sponsor=cls.admin)
        cls.sponsor_key = cls._key(cls.sponsor)

    @classmethod
    def _make_member(cls, login, sponsor):
        """Membre portail actif, parrainé par ``sponsor``, comme le ferait l'application."""
        user = new_test_user(cls.env, login=login, groups='base.group_portal')
        cls.env['club_social_profile.profile'].sudo().get_or_create_for_user(user)
        cls.env['social_reputation.vouching'].with_user(sponsor).sudo().vouch_for(user)
        membership = cls.env['club_membership.membership'].sudo().create({
            'partner_id': user.partner_id.id,
            'membership_type_id': cls.env.ref('club_membership.membership_type_regular').id,
        })
        membership.action_activate()
        return user

    @classmethod
    def _key(cls, user):
        key, _expiration = cls.env['res.users.apikeys'].with_user(user)._social_mobile_generate('test')
        return key

    def call(self, method, path, key=None, body=None, headers=None):
        all_headers = {'Content-Type': 'application/json', **(headers or {})}
        if key:
            all_headers['Authorization'] = f'Bearer {key}'
        data = json.dumps(body) if body is not None else None
        return self.url_open(API + path, data=data, headers=all_headers, method=method)

    def enroll(self, email='nouveau@example.com'):
        res = self.call('POST', '/enroll', body={'email': email, 'device_name': 'iPhone', 'consent': True})
        self.assertEqual(res.status_code, 201, res.text)
        return res.json()

    def code(self, enrollment, steps_ago=0):
        step = int(fields.Datetime.now().timestamp() // PERIOD) - steps_ago
        return {'enrollment_id': enrollment['enrollment_id'], 'code': totp(enrollment['qr_secret'], step)}

    def poll(self, enrollment, secret=None):
        return self.call('GET', f"/enroll/{enrollment['enrollment_id']}",
                         headers={'X-Enrollment-Secret': secret or enrollment['poll_secret']})

    # ── Parcours complet ─────────────────────────────────────────────────────

    def test_sponsored_newcomer_becomes_member(self):
        enrollment = self.enroll()
        self.assertEqual(self.poll(enrollment).json()['state'], 'pending')

        preview = self.call('POST', '/sponsor/preview', key=self.sponsor_key, body=self.code(enrollment))
        self.assertEqual(preview.status_code, 200, preview.text)
        self.assertEqual(preview.json()['email'], 'nouveau@example.com')
        self.assertTrue(preview.json()['can_sponsor'])

        confirm = self.call('POST', '/sponsor/confirm', key=self.sponsor_key,
                            body=dict(self.code(enrollment), statement="Rencontré au club"))
        self.assertEqual(confirm.status_code, 200, confirm.text)
        # Confirmer deux fois (réseau lent) ne crée rien de plus.
        again = self.call('POST', '/sponsor/confirm', key=self.sponsor_key, body=self.code(enrollment))
        self.assertEqual(again.json()['newcomer']['id'], confirm.json()['newcomer']['id'])

        newcomer = self.env['res.users'].browse(confirm.json()['newcomer']['id'])
        self.assertTrue(newcomer.share, "un nouveau membre est un utilisateur portail")
        self.assertTrue(newcomer.has_group('social_base.group_social_user'))
        vouching = self.env['social_reputation.vouching'].sudo().search([('newcomer_id', '=', newcomer.id)])
        self.assertEqual(vouching.sponsor_id, self.sponsor)
        self.assertEqual(vouching.state, 'active')
        self.assertEqual(vouching.statement, "Rencontré au club")

        self.assertTrue(newcomer.name.startswith("Nouveau membre"), "jamais un nom tiré du courriel")
        self.assertNotIn('nouveau', newcomer.name.lower().replace('nouveau membre', ''))
        consent = self.env['social_privacy.consent'].sudo().search([('user_id', '=', newcomer.id)])
        self.assertEqual(consent.policy_version_id, self.policy)
        self.assertEqual(consent.source, 'api')

        # Réponse perdue : l'appareil redemande et reçoit une nouvelle clé ; la première est supprimée.
        lost = self.poll(enrollment).json()
        self.assertEqual(lost['state'], 'active')
        status = self.poll(enrollment).json()
        self.assertEqual(status['state'], 'active')
        self.assertEqual(self.call('GET', '/me', key=lost['key']).status_code, 401)

        # Une clé de portée social_mobile ouvre l'API pour un utilisateur portail.
        me = self.call('GET', '/me', key=status['key'])
        self.assertEqual(me.status_code, 200, me.text)
        self.assertTrue(me.json()['is_member'])
        self.assertTrue(me.json()['can_sponsor'], "un membre parrainé peut parrainer à son tour")
        # Premier appel authentifié : l'inscription et son courriel sont effacés.
        self.assertEqual(self.poll(enrollment).status_code, 404)
        self.assertFalse(self.env['social_mobile.enrollment'].sudo().search([('email', '=', 'nouveau@example.com')]))

    def test_enroll_requires_current_policy(self):
        self.assertEqual(self.call('GET', '/policy').json()['version'], '9.9')
        self.policy.is_active = False
        res = self.call('POST', '/enroll', body={'email': 'x@example.com', 'consent': True})
        self.assertEqual(res.status_code, 429)
        self.assertEqual(self.call('GET', '/policy').status_code, 404)

    # ── Refus ────────────────────────────────────────────────────────────────

    def test_enroll_validation(self):
        self.assertEqual(self.call('POST', '/enroll', body={'email': 'pas-un-courriel', 'consent': True}).status_code, 400)
        self.assertEqual(self.call('POST', '/enroll', body={'email': 'a@example.com'}).status_code, 400)
        for _i in range(3):
            self.enroll('repete@example.com')
        res = self.call('POST', '/enroll', body={'email': 'repete@example.com', 'consent': True})
        self.assertEqual(res.status_code, 429)

    def test_existing_account_is_not_revealed_to_newcomer(self):
        # Le nouveau venu ne doit pas pouvoir tester si un courriel est membre du club.
        enrollment = self.enroll('sponsor.mobile@example.com')
        res = self.call('POST', '/sponsor/confirm', key=self.sponsor_key, body=self.code(enrollment))
        self.assertEqual(res.status_code, 409)
        self.assertEqual(self.poll(enrollment).json()['state'], 'pending')

    def test_wrong_secret_and_stale_code(self):
        enrollment = self.enroll()
        self.assertEqual(self.poll(enrollment, secret='mauvais').status_code, 404)
        stale = self.code(enrollment, steps_ago=10)
        self.assertEqual(self.call('POST', '/sponsor/preview', key=self.sponsor_key, body=stale).status_code, 404)
        forged = {'enrollment_id': enrollment['enrollment_id'], 'code': '0' * 10}
        self.assertEqual(self.call('POST', '/sponsor/confirm', key=self.sponsor_key, body=forged).status_code, 404)

    def test_ineligible_sponsor(self):
        enrollment = self.enroll()
        outsider = new_test_user(self.env, login='pas.membre@example.com', groups='base.group_portal')
        res = self.call('POST', '/sponsor/confirm', key=self._key(outsider), body=self.code(enrollment))
        self.assertEqual(res.status_code, 409)

        # Un membre dont le parrainage a été retiré perd l'accès, donc le droit de parrainer.
        orphan = self._make_member('orphelin@example.com', sponsor=self.admin)
        vouching = self.env['social_reputation.vouching'].sudo().search([('newcomer_id', '=', orphan.id)])
        vouching.with_user(self.admin).action_withdraw(reason="test")
        self.assertIsNotNone(orphan._social_mobile_sponsor_refusal())

    def test_other_sponsor_cannot_take_over(self):
        enrollment = self.enroll()
        self.call('POST', '/sponsor/confirm', key=self.sponsor_key, body=self.code(enrollment))
        other = self._make_member('autre.parrain@example.com', sponsor=self.admin)
        res = self.call('POST', '/sponsor/confirm', key=self._key(other), body=self.code(enrollment))
        self.assertEqual(res.status_code, 409)

    def test_keys_are_scoped(self):
        self.assertEqual(self.call('GET', '/me').status_code, 401)
        rpc_key = self.env['res.users.apikeys'].with_user(self.sponsor).sudo()._generate('rpc', 'rpc', None)
        self.assertEqual(self.call('GET', '/me', key=rpc_key).status_code, 401)
        res = self.url_open('/json/2/res.partner/search', data='{"domain": []}', method='POST',
                            headers={'Authorization': f'Bearer {self.sponsor_key}', 'Content-Type': 'application/json'})
        self.assertEqual(res.status_code, 401)

    def test_renew_and_delete_account(self):
        member = self._make_member('a.supprimer@example.com', sponsor=self.admin)
        key = self._key(member)
        renewed = self.call('POST', '/token/renew', key=key, body={'device_name': 'iPhone'})
        self.assertEqual(renewed.status_code, 200)
        new_key = renewed.json()['key']
        self.assertEqual(self.call('GET', '/me', key=new_key).status_code, 200)
        self.assertEqual(self.call('GET', '/me', key=key).status_code, 200, "délai de grâce de l'ancienne clé")

        self.assertEqual(self.call('DELETE', '/me', key=new_key).status_code, 200)
        self.assertFalse(member.active)
        self.assertEqual(self.call('GET', '/me', key=new_key).status_code, 401)

    def test_review_code(self):
        self.assertEqual(self.call('POST', '/enroll/review', body={'code': 'x'}).status_code, 404)
        demo = self._make_member('demo.apple@example.com', sponsor=self.admin)
        ICP = self.env['ir.config_parameter'].sudo()
        ICP.set_int('social_mobile.review_user_id', demo.id)
        ICP.set_str('social_mobile.review_code', 'APPLE-2026')
        self.assertEqual(self.call('POST', '/enroll/review', body={'code': 'mauvais'}).status_code, 404)
        res = self.call('POST', '/enroll/review', body={'code': 'APPLE-2026'})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(self.call('GET', '/me', key=res.json()['key']).json()['user']['id'], demo.id)

    def test_purge(self):
        enrollment = self.enroll('vieux@example.com')
        record = self.env['social_mobile.enrollment'].sudo().search([('uuid', '=', enrollment['enrollment_id'])])
        record.write({'expires_at': fields.Datetime.now()})
        self.env['social_mobile.enrollment']._cron_purge()
        self.assertFalse(record.exists())
