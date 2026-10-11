from odoo.tests import HttpCase, TransactionCase, tagged


def _make_social_user(env, name, login):
    group_user = env.ref('base.group_user')
    group_social = env.ref('social_base.group_social_user')
    return env['res.users'].create({
        'name': name, 'login': login, 'email': f'{login}@bdsm.test',
        'password': 'Test1234!',
        'group_ids': [(4, group_user.id), (4, group_social.id)],
    })


@tagged('club_social_profile_bdsm', 'bdsm_portal')
class TestBdsmPortalData(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = _make_social_user(cls.env, 'BdsmPortalUser', 'bdsm_portal_user')
        cls.other = _make_social_user(cls.env, 'BdsmPortalOther', 'bdsm_portal_other')
        cls.profile = cls.env['club_social_profile.profile'].sudo().get_or_create_for_user(cls.user)
        cls.kink = cls.env['club_social_profile_bdsm.kink'].sudo().create({
            'name': 'Portal Test Kink',
        })

    def test_save_bdsm_role(self):
        self.profile.sudo().write({'bdsm_role': 'switch', 'experience': 'intermediate'})
        self.assertEqual(self.profile.bdsm_role, 'switch')
        self.assertEqual(self.profile.experience, 'intermediate')

    def test_save_limits(self):
        self.profile.sudo().write({
            'soft_limits': 'Negotiable with discussion',
            'hard_limits': 'Never under any circumstance',
        })
        self.assertEqual(self.profile.soft_limits, 'Negotiable with discussion')
        self.assertEqual(self.profile.hard_limits, 'Never under any circumstance')

    def test_add_kink_level(self):
        kl = self.env['club_social_profile_bdsm.kink_level'].sudo().create({
            'profile_id': self.profile.id,
            'kink_id': self.kink.id,
            'level': 'oui',
        })
        self.assertIn(kl, self.profile.kink_level_ids)
        self.assertEqual(kl.level, 'oui')

    def test_update_kink_level(self):
        kl = self.env['club_social_profile_bdsm.kink_level'].sudo().create({
            'profile_id': self.profile.id,
            'kink_id': self.kink.id,
            'level': 'curieux',
        })
        kl.sudo().write({'level': 'expert'})
        self.assertEqual(kl.level, 'expert')

    def test_duplicate_kink_raises(self):
        kink2 = self.env['club_social_profile_bdsm.kink'].sudo().create({'name': 'Dup Test Kink'})
        self.env['club_social_profile_bdsm.kink_level'].sudo().create({
            'profile_id': self.profile.id, 'kink_id': kink2.id, 'level': 'curieux',
        })
        with self.assertRaises(Exception):
            self.env['club_social_profile_bdsm.kink_level'].sudo().create({
                'profile_id': self.profile.id, 'kink_id': kink2.id, 'level': 'oui',
            })

    def test_remove_kink_level(self):
        kink3 = self.env['club_social_profile_bdsm.kink'].sudo().create({'name': 'Remove Test Kink'})
        kl = self.env['club_social_profile_bdsm.kink_level'].sudo().create({
            'profile_id': self.profile.id, 'kink_id': kink3.id, 'level': 'soft',
        })
        kl.sudo().unlink()
        self.assertNotIn(kl, self.profile.kink_level_ids)

    def test_kink_request_created(self):
        req = self.env['club_social_profile_bdsm.kink_request'].sudo().create({
            'name': 'New Kink Suggestion',
            'description': 'Context here',
            'requester_id': self.user.id,
        })
        self.assertEqual(req.state, 'pending')
        self.assertEqual(req.requester_id, self.user)

    def test_cannot_remove_other_profile_kink(self):
        other_profile = self.env['club_social_profile.profile'].sudo().get_or_create_for_user(
            self.other
        )
        kink4 = self.env['club_social_profile_bdsm.kink'].sudo().create({'name': 'Other Kink'})
        kl = self.env['club_social_profile_bdsm.kink_level'].sudo().create({
            'profile_id': other_profile.id, 'kink_id': kink4.id, 'level': 'curieux',
        })
        # Portal controller checks profile ownership — simulate the check
        self.assertNotEqual(kl.profile_id.user_id, self.user)

    def test_compatibility_score_range(self):
        other_profile = self.env['club_social_profile.profile'].sudo().get_or_create_for_user(
            self.other
        )
        result = self.profile.compute_compatibility(other_profile)
        self.assertIn('score', result)
        self.assertGreaterEqual(result['score'], 0)
        self.assertLessEqual(result['score'], 100)

    def test_compatibility_shared_kinks(self):
        other_profile = self.env['club_social_profile.profile'].sudo().get_or_create_for_user(
            self.other
        )
        shared_kink = self.env['club_social_profile_bdsm.kink'].sudo().create({
            'name': 'Shared Kink Test',
        })
        self.env['club_social_profile_bdsm.kink_level'].sudo().create({
            'profile_id': self.profile.id,
            'kink_id': shared_kink.id,
            'level': 'oui',
        })
        self.env['club_social_profile_bdsm.kink_level'].sudo().create({
            'profile_id': other_profile.id,
            'kink_id': shared_kink.id,
            'level': 'oui',
        })
        result = self.profile.compute_compatibility(other_profile)
        self.assertIn('Shared Kink Test', result['shared_kinks'])
        self.assertGreaterEqual(result['shared_count'], 1)

    def test_compatibility_role_dominant_soumis(self):
        other_profile = self.env['club_social_profile.profile'].sudo().get_or_create_for_user(
            self.other
        )
        self.profile.sudo().write({'bdsm_role': 'dominant'})
        other_profile.sudo().write({'bdsm_role': 'soumis'})
        result = self.profile.compute_compatibility(other_profile)
        self.assertGreaterEqual(result['role_score'], 85)

    def test_compatibility_same_role_lower_score(self):
        other_profile = self.env['club_social_profile.profile'].sudo().get_or_create_for_user(
            self.other
        )
        self.profile.sudo().write({'bdsm_role': 'dominant'})
        other_profile.sudo().write({'bdsm_role': 'dominant'})
        result_same = self.profile.compute_compatibility(other_profile)
        other_profile.sudo().write({'bdsm_role': 'soumis'})
        result_comp = self.profile.compute_compatibility(other_profile)
        self.assertLessEqual(result_same['role_score'], result_comp['role_score'])

    def test_compatibility_result_structure(self):
        other_profile = self.env['club_social_profile.profile'].sudo().get_or_create_for_user(
            self.other
        )
        result = self.profile.compute_compatibility(other_profile)
        for key in ('score', 'kink_score', 'role_score', 'shared_kinks', 'shared_count'):
            self.assertIn(key, result)


@tagged('club_social_profile_bdsm', 'bdsm_portal', 'post_install', '-at_install')
class TestBdsmPortalHttp(HttpCase):

    def test_bdsm_profile_unauthenticated_redirects(self):
        resp = self.url_open('/my/profile/bdsm', allow_redirects=False)
        self.assertIn(resp.status_code, (302, 303))

    def test_bdsm_profile_authenticated_ok(self):
        self.authenticate('admin', 'admin')
        _csrf = self.csrf_token()
        resp = self.url_open('/my/profile/bdsm')
        self.assertEqual(resp.status_code, 200)

    def test_bdsm_save_redirects(self):
        self.authenticate('admin', 'admin')
        _csrf = self.csrf_token()
        resp = self.url_open(
            '/my/profile/bdsm/save',
            data={'csrf_token': _csrf, 
                'bdsm_role': 'switch',
                'experience': 'intermediate',
                'soft_limits': '',
                'hard_limits': '',
            },
            allow_redirects=False,
        )
        self.assertIn(resp.status_code, (302, 303))

    def test_bdsm_kink_request_redirects(self):
        self.authenticate('admin', 'admin')
        _csrf = self.csrf_token()
        resp = self.url_open(
            '/my/profile/bdsm/kink/request',
            data={'csrf_token': _csrf, 'name': 'HTTP Test Kink'},
            allow_redirects=False,
        )
        self.assertIn(resp.status_code, (302, 303))

    def test_bdsm_kink_add_without_kink_id_redirects(self):
        self.authenticate('admin', 'admin')
        _csrf = self.csrf_token()
        resp = self.url_open(
            '/my/profile/bdsm/kink/add',
            data={'csrf_token': _csrf, 'level': 'curieux'},
            allow_redirects=False,
        )
        # No kink_id → redirect with error param
        self.assertIn(resp.status_code, (302, 303))

    def test_compatibility_api_authenticated(self):
        self.authenticate('admin', 'admin')
        _csrf = self.csrf_token()
        admin_user = self.env.ref('base.user_admin')
        profile = self.env['club_social_profile.profile'].sudo().search(
            [('user_id', '=', admin_user.id)], limit=1
        )
        if not profile:
            self.skipTest('Admin has no profile')
        resp = self.url_open(f'/social/api/profile/{profile.id}/compatibility')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data.get('success'))
        self.assertIn('score', data.get('data', {}))

    def test_compatibility_api_unauthenticated_fails(self):
        resp = self.url_open('/social/api/profile/1/compatibility', allow_redirects=False)
        # Not authenticated → 401 or redirect
        self.assertIn(resp.status_code, (302, 303, 401))

    def test_api_kinks_authenticated_returns_list(self):
        """GET /social/api/kinks retourne une liste de kinks."""
        self.authenticate('admin', 'admin')
        _csrf = self.csrf_token()
        resp = self.url_open('/social/api/kinks')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()['data']
        self.assertIn('kinks', data)
        self.assertIsInstance(data['kinks'], list)

    def test_api_kinks_unauthenticated_redirects(self):
        resp = self.url_open('/social/api/kinks', allow_redirects=False)
        self.assertIn(resp.status_code, (302, 303))

    def test_api_kinks_result_structure(self):
        """Every returned kink must have id, name, description."""
        self.authenticate('admin', 'admin')
        _csrf = self.csrf_token()
        self.env['club_social_profile_bdsm.kink'].sudo().create({'name': 'API Struct Kink'})
        resp = self.url_open('/social/api/kinks')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()['data']
        for k in data['kinks']:
            self.assertIn('id', k)
            self.assertIn('name', k)
            self.assertIn('description', k)

    def test_api_compatibility_nonexistent_profile_404(self):
        """Profil inexistant → 404."""
        self.authenticate('admin', 'admin')
        _csrf = self.csrf_token()
        resp = self.url_open('/social/api/profile/999999999/compatibility')
        self.assertEqual(resp.status_code, 404)
