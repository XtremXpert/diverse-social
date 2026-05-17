from odoo.tests import TransactionCase, tagged
from odoo.exceptions import ValidationError


@tagged('social_discovery', 'discovery')
class TestDiscovery(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        group_user = cls.env.ref('social_base.group_social_user')

        def make_user(name, login, email):
            return cls.env['res.users'].create({
                'name': name, 'login': login, 'email': email,
                'group_ids': [(4, group_user.id)],
            })

        cls.searcher_user = make_user('Searcher', 'disc_searcher', 'searcher@disc.test')
        cls.alice = make_user('Alice', 'disc_alice', 'alice@disc.test')
        cls.bob = make_user('Bob', 'disc_bob', 'bob@disc.test')
        cls.carol = make_user('Carol', 'disc_carol', 'carol@disc.test')
        cls.private_user = make_user('Private', 'disc_private', 'priv@disc.test')

        Profile = cls.env['club_social_profile.profile']
        cls.searcher = Profile.get_or_create_for_user(cls.searcher_user)
        cls.alice_p = Profile.get_or_create_for_user(cls.alice)
        cls.bob_p = Profile.get_or_create_for_user(cls.bob)
        cls.carol_p = Profile.get_or_create_for_user(cls.carol)
        cls.private_p = Profile.get_or_create_for_user(cls.private_user)

        # Set up profiles
        cls.alice_p.write({
            'gender': 'femme', 'orientation': 'bi',
            'availability': 'disponible', 'birth_year': 1990,
            'city': 'Montréal', 'visibility': 'members',
        })
        cls.bob_p.write({
            'gender': 'homme', 'orientation': 'hetero',
            'availability': 'couple_ouvert', 'birth_year': 1985,
            'city': 'Québec', 'visibility': 'members',
        })
        cls.carol_p.write({
            'gender': 'non_binaire', 'orientation': 'pan',
            'availability': 'disponible', 'birth_year': 1995,
            'city': 'Montréal', 'visibility': 'members',
        })
        cls.private_p.write({'visibility': 'connections'})

        cls.Criteria = cls.env['social_discovery.criteria']

    def _make_criteria(self, **kwargs):
        vals = {'profile_id': self.searcher.id, 'name': 'Test'}
        vals.update(kwargs)
        return self.Criteria.create(vals)

    # ── Basic filtering ───────────────────────────────────────────────────────

    def test_excludes_self(self):
        crit = self._make_criteria()
        profiles = crit._find_profiles()
        self.assertNotIn(self.searcher, profiles)

    def test_excludes_connections_only_visibility(self):
        crit = self._make_criteria()
        profiles = crit._find_profiles()
        self.assertNotIn(self.private_p, profiles)

    def test_no_filter_returns_members(self):
        crit = self._make_criteria()
        profiles = crit._find_profiles()
        self.assertIn(self.alice_p, profiles)
        self.assertIn(self.bob_p, profiles)
        self.assertIn(self.carol_p, profiles)

    # ── Age filter ────────────────────────────────────────────────────────────

    def test_age_min_filter(self):
        # alice born 1990 → ~36, carol born 1995 → ~31
        crit = self._make_criteria(min_age=35)
        profiles = crit._find_profiles()
        self.assertIn(self.alice_p, profiles)
        self.assertNotIn(self.carol_p, profiles)

    def test_age_max_filter(self):
        # bob born 1985 → ~41
        crit = self._make_criteria(max_age=38)
        profiles = crit._find_profiles()
        self.assertNotIn(self.bob_p, profiles)

    def test_age_min_must_be_18(self):
        with self.assertRaises(ValidationError):
            self._make_criteria(min_age=17)

    def test_age_range_consistency(self):
        with self.assertRaises(ValidationError):
            self._make_criteria(min_age=30, max_age=25)

    # ── City filter ───────────────────────────────────────────────────────────

    def test_city_filter(self):
        crit = self._make_criteria(city='Montréal')
        profiles = crit._find_profiles()
        self.assertIn(self.alice_p, profiles)
        self.assertIn(self.carol_p, profiles)
        self.assertNotIn(self.bob_p, profiles)

    def test_city_partial_match(self):
        crit = self._make_criteria(city='mont')
        profiles = crit._find_profiles()
        self.assertIn(self.alice_p, profiles)

    # ── Gender filter ─────────────────────────────────────────────────────────

    def test_gender_filter(self):
        femme_val = self.env.ref('social_discovery.gender_femme')
        crit = self._make_criteria(gender_ids=[(4, femme_val.id)])
        profiles = crit._find_profiles()
        self.assertIn(self.alice_p, profiles)
        self.assertNotIn(self.bob_p, profiles)
        self.assertNotIn(self.carol_p, profiles)

    def test_gender_multi_filter(self):
        femme_val = self.env.ref('social_discovery.gender_femme')
        nb_val = self.env.ref('social_discovery.gender_non_binaire')
        crit = self._make_criteria(gender_ids=[(4, femme_val.id), (4, nb_val.id)])
        profiles = crit._find_profiles()
        self.assertIn(self.alice_p, profiles)
        self.assertIn(self.carol_p, profiles)
        self.assertNotIn(self.bob_p, profiles)

    # ── Availability filter ───────────────────────────────────────────────────

    def test_availability_filter(self):
        disp_val = self.env.ref('social_discovery.avail_disponible')
        crit = self._make_criteria(availability_ids=[(4, disp_val.id)])
        profiles = crit._find_profiles()
        self.assertIn(self.alice_p, profiles)
        self.assertIn(self.carol_p, profiles)
        self.assertNotIn(self.bob_p, profiles)

    # ── Circles filter ────────────────────────────────────────────────────────

    def test_in_circles_only(self):
        # Alice puts searcher in a circle; bob does not
        friends_type = self.env['social_circles.circle_type'].sudo().create({
            'name': 'Friends',
        })
        alice_circle = self.alice_p.ensure_circle(friends_type)
        alice_circle.add_member(self.searcher_user)

        crit = self._make_criteria(in_circles_only=True)
        profiles = crit._find_profiles()
        self.assertIn(self.alice_p, profiles)
        self.assertNotIn(self.bob_p, profiles)

    # ── Single default constraint ──────────────────────────────────────────────

    def test_single_default_constraint(self):
        self._make_criteria(name='Default 1', is_default=True)
        with self.assertRaises(ValidationError):
            self._make_criteria(name='Default 2', is_default=True)

    # ── Result count ─────────────────────────────────────────────────────────

    def test_result_count_computed(self):
        crit = self._make_criteria()
        self.assertGreater(crit.result_count, 0)

    # ── Orientation filter ────────────────────────────────────────────────────

    def test_orientation_filter(self):
        bi_val = self.env.ref('social_discovery.orient_bi')
        crit = self._make_criteria(orientation_ids=[(4, bi_val.id)])
        profiles = crit._find_profiles()
        self.assertIn(self.alice_p, profiles)
        self.assertNotIn(self.bob_p, profiles)

    # ── age_verified / onboarding_done filters ────────────────────────────────

    def test_age_verified_filter(self):
        """Filtre age_verified : seuls les profils vérifiés retenus."""
        self.alice_p.sudo().write({'birth_year': 1990})
        self.carol_p.sudo().write({'birth_year': 0})
        crit = self._make_criteria(age_verified=True)
        profiles = crit._find_profiles()
        for p in profiles:
            self.assertTrue(p.age_verified)

    def test_onboarding_done_filter(self):
        self.alice_p.sudo().write({'onboarding_done': True})
        self.bob_p.sudo().write({'onboarding_done': False})
        crit = self._make_criteria(onboarding_done=True)
        profiles = crit._find_profiles()
        self.assertNotIn(self.bob_p, profiles)
        for p in profiles:
            self.assertTrue(p.onboarding_done)

    # ── max_age=0 allowed ─────────────────────────────────────────────────────

    def test_max_age_zero_no_upper_limit(self):
        """max_age=0 (défaut) ne doit pas lever d'erreur et ne filtre pas."""
        crit = self._make_criteria(max_age=0)
        profiles = crit._find_profiles()
        self.assertIn(self.alice_p, profiles)
        self.assertIn(self.bob_p, profiles)

    # ── reachable_only / _is_reachable ────────────────────────────────────────

    def test_is_reachable_no_gate(self):
        """_is_reachable retourne True si le profil cible n'a pas de gate active."""
        crit = self._make_criteria()
        result = crit._is_reachable(self.alice_p, self.searcher_user)
        self.assertTrue(result)

    def test_is_reachable_with_gate_no_request(self):
        """_is_reachable retourne False si gate active sans demande approuvée."""
        if 'social_consent.gate' not in self.env:
            self.skipTest('social_consent not installed')
        gate = self.env['social_consent.gate'].sudo().create({
            'profile_id': self.bob_p.id,
            'is_active': True,
        })
        crit = self._make_criteria()
        result = crit._is_reachable(self.bob_p, self.searcher_user)
        self.assertFalse(result)

    def test_reachable_only_excludes_gated(self):
        if 'social_consent.gate' not in self.env:
            self.skipTest('social_consent not installed')
        self.env['social_consent.gate'].sudo().create({
            'profile_id': self.carol_p.id,
            'is_active': True,
        })
        crit = self._make_criteria(reachable_only=True)
        profiles = crit._find_profiles()
        self.assertNotIn(self.carol_p, profiles)
        self.assertIn(self.alice_p, profiles)

    # ── action_open_discovery ─────────────────────────────────────────────────

    def test_action_open_discovery_no_default_returns_list(self):
        """Sans recherche par défaut → action liste les critères."""
        action = self.searcher.action_open_discovery()
        self.assertEqual(action['type'], 'ir.actions.act_window')
        self.assertEqual(action['res_model'], 'social_discovery.criteria')

    def test_action_open_discovery_with_default_runs_search(self):
        crit = self._make_criteria(name='Défaut', is_default=True)
        action = self.searcher.action_open_discovery()
        self.assertEqual(action['res_model'], 'club_social_profile.profile')

    # ── discovery_criteria_count ──────────────────────────────────────────────

    def test_discovery_criteria_count(self):
        before = self.searcher.discovery_criteria_count
        self._make_criteria(name='Count Test')
        self.searcher.invalidate_recordset(['discovery_criteria_count'])
        self.assertEqual(self.searcher.discovery_criteria_count, before + 1)

    # ── action_search returns act_window ──────────────────────────────────────

    def test_action_search_returns_window(self):
        crit = self._make_criteria()
        action = crit.action_search()
        self.assertEqual(action['type'], 'ir.actions.act_window')
        self.assertEqual(action['res_model'], 'club_social_profile.profile')

    def test_action_search_domain_contains_matching_ids(self):
        crit = self._make_criteria(city='Montréal')
        action = crit.action_search()
        self.assertIn(('id', 'in', crit._find_profiles().ids), action['domain'])
