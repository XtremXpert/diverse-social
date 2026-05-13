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
        alice_circle = self.alice_p.ensure_circle('Friends')
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

    # ── action_search returns act_window ──────────────────────────────────────

    def test_action_search_returns_window(self):
        crit = self._make_criteria()
        action = crit.action_search()
        self.assertEqual(action['type'], 'ir.actions.act_window')
        self.assertEqual(action['res_model'], 'club_social_profile.profile')
