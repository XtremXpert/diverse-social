import base64
import datetime
import io
import json

from PIL import Image

from odoo.tests import HttpCase, new_test_user, tagged

API = '/api/social/v1'


def png(width=600, height=300):
    buffer = io.BytesIO()
    Image.new('RGB', (width, height), (120, 40, 140)).save(buffer, format='PNG')
    return buffer.getvalue()


@tagged('post_install', '-at_install')
class TestProfile(HttpCase):
    """Accueil dans l'application : les trois étapes de /onboarding, année de naissance obligatoire."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = new_test_user(cls.env, login='accueil.mobile@example.com', groups='base.group_portal')
        cls.profile = cls.env['club_social_profile.profile'].sudo().get_or_create_for_user(cls.user)
        cls.key, _expiration = cls.env['res.users.apikeys'].with_user(cls.user)._social_mobile_generate('test')
        cls.looking_for = cls.env['club_social_profile.looking_for'].sudo().create({'name': "Amitié"})
        cls.language = cls.env['club_social_profile.language'].sudo().create({'name': "Français"})

    def call(self, method, path, body=None):
        headers = {'Content-Type': 'application/json', 'Authorization': f'Bearer {self.key}'}
        data = json.dumps(body) if body is not None else None
        return self.url_open(API + path, data=data, headers=headers, method=method)

    def test_read_profile_and_options(self):
        res = self.call('GET', '/profile')
        self.assertEqual(res.status_code, 200, res.text)
        payload = res.json()
        self.assertFalse(payload['onboarding_done'])
        self.assertEqual(payload['adult_age'], 18)
        self.assertIsNone(payload['profile']['birth_year'])
        self.assertFalse(payload['profile']['has_photo'])
        options = payload['options']
        self.assertIn('non_binaire', [o['value'] for o in options['gender']])
        self.assertIn('members', [o['value'] for o in options['visibility']])
        self.assertIn({'id': self.looking_for.id, 'name': "Amitié"}, options['looking_for_ids'])
        self.assertIn({'id': self.language.id, 'name': "Français"}, options['language_ids'])
        self.assertTrue(all(o['label'] for o in options['orientation']), "chaque choix a un libellé")
        # /me le dit aussi : c'est ce que l'application lit pour imposer l'accueil.
        self.assertFalse(self.call('GET', '/me').json()['onboarding_done'])

    def test_update_writes_only_given_fields(self):
        adult = datetime.date.today().year - 30
        res = self.call('POST', '/profile', {
            'pronouns': ' iel ', 'bio': "Bonjour", 'birth_year': adult, 'city': "Québec",
            'gender': 'non_binaire', 'orientation': 'pan', 'availability': 'disponible',
            'visibility': 'connections', 'digest_email_enabled': False,
            'looking_for_ids': [self.looking_for.id, 999999], 'language_ids': [self.language.id],
        })
        self.assertEqual(res.status_code, 200, res.text)
        p = self.profile
        self.assertEqual((p.pronouns, p.bio, p.birth_year, p.city), ('iel', "Bonjour", adult, "Québec"))
        self.assertEqual((p.gender, p.orientation, p.availability, p.visibility),
                         ('non_binaire', 'pan', 'disponible', 'connections'))
        self.assertFalse(p.digest_email_enabled)
        self.assertEqual(p.looking_for_ids, self.looking_for, "identifiant inconnu ignoré")
        self.assertEqual(p.language_ids, self.language)
        self.assertFalse(p.onboarding_done, "modifier le profil ne termine pas l'accueil")

        self.call('POST', '/profile', {'city': "Lévis"})
        self.assertEqual((p.city, p.bio, p.birth_year), ("Lévis", "Bonjour", adult), "le reste ne bouge pas")

    def test_invalid_values_are_refused(self):
        this_year = datetime.date.today().year
        for body in ({'birth_year': this_year - 17}, {'birth_year': 1850}, {'birth_year': 'abc'},
                     {'gender': 'inconnu'}, {'looking_for_ids': 'tout'}, {'bio': 12},
                     {'onboarding_done': True, 'gender': 'x'}):
            res = self.call('POST', '/profile', body)
            self.assertEqual(res.status_code, 422, body)
        self.assertFalse(self.profile.birth_year)
        # Le drapeau ne s'écrit pas par /profile, même seul.
        self.assertEqual(self.call('POST', '/profile', {'onboarding_done': True}).status_code, 200)
        self.assertFalse(self.profile.onboarding_done)

    def test_complete_requires_adult_birth_year(self):
        res = self.call('POST', '/profile/complete')
        self.assertEqual(res.status_code, 422)
        self.assertEqual(res.json()['error']['code'], 'birth_year_required')
        self.assertFalse(self.profile.onboarding_done)

        self.call('POST', '/profile', {'birth_year': datetime.date.today().year - 18})
        res = self.call('POST', '/profile/complete')
        self.assertEqual(res.status_code, 200, res.text)
        self.assertTrue(self.profile.onboarding_done)
        self.assertTrue(self.call('GET', '/me').json()['onboarding_done'])

    def test_photo(self):
        res = self.call('POST', '/profile/photo', {'data': base64.b64encode(png()).decode()})
        self.assertEqual(res.status_code, 200, res.text)
        self.assertTrue(res.json()['has_photo'])
        with Image.open(io.BytesIO(self.profile.profile_image.content)) as image:
            self.assertLessEqual(max(image.size), 400, "réduite comme sur le site")
        self.assertTrue(self.call('GET', '/profile').json()['profile']['has_photo'])

        self.assertEqual(self.call('POST', '/profile/photo', {'data': 'pas du base64 !'}).status_code, 400)
        res = self.call('POST', '/profile/photo', {'data': base64.b64encode(b'pas une image').decode()})
        self.assertEqual(res.status_code, 422)

    def test_requires_mobile_key(self):
        res = self.url_open(API + '/profile', headers={'Authorization': 'Bearer faux'})
        self.assertEqual(res.status_code, 401)
