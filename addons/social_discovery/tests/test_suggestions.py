from odoo.tests import TransactionCase, tagged


def _make_social_user(env, login):
    group_user = env.ref('base.group_user')
    group_social = env.ref('social_base.group_social_user')
    user = env['res.users'].create({
        'name': login.capitalize(),
        'login': login,
        'email': f'{login}@sug.test',
        'password': 'Test1234!',
        'group_ids': [(4, group_user.id), (4, group_social.id)],
    })
    profile = env['club_social_profile.profile'].sudo().get_or_create_for_user(user)
    profile.onboarding_done = True
    profile.visibility = 'members'
    return user, profile


@tagged('social_discovery', 'suggestions', 'post_install', '-at_install')
class TestSuggestionService(TransactionCase):

    def setUp(self):
        super().setUp()
        self.alice_user, self.alice = _make_social_user(self.env, 'sug_alice')
        self.bob_user,   self.bob   = _make_social_user(self.env, 'sug_bob')
        self.carol_user, self.carol = _make_social_user(self.env, 'sug_carol')
        self.Service = self.env['social_discovery.suggestion_service']

    def test_excludes_self(self):
        results = self.Service.get_suggestions(user=self.alice_user)
        ids = [r['profile'].user_id.id for r in results]
        self.assertNotIn(self.alice_user.id, ids)

    def test_returns_candidates(self):
        results = self.Service.get_suggestions(user=self.alice_user)
        user_ids = [r['profile'].user_id.id for r in results]
        self.assertIn(self.bob_user.id, user_ids)
        self.assertIn(self.carol_user.id, user_ids)

    def test_excludes_when_viewer_onboarding_incomplete(self):
        self.alice.onboarding_done = False
        results = self.Service.get_suggestions(user=self.alice_user)
        self.assertEqual(results, [])

    def test_excludes_when_target_onboarding_incomplete(self):
        self.bob.onboarding_done = False
        results = self.Service.get_suggestions(user=self.alice_user)
        user_ids = [r['profile'].user_id.id for r in results]
        self.assertNotIn(self.bob_user.id, user_ids)

    def test_excludes_already_connected(self):
        self.env['club_social_profile.connection'].create({
            'user_id': self.alice_user.id,
            'connected_user_id': self.bob_user.id,
            'state': 'accepted',
        })
        results = self.Service.get_suggestions(user=self.alice_user)
        user_ids = [r['profile'].user_id.id for r in results]
        self.assertNotIn(self.bob_user.id, user_ids)

    def test_excludes_pending_connection(self):
        self.env['club_social_profile.connection'].create({
            'user_id': self.alice_user.id,
            'connected_user_id': self.bob_user.id,
            'state': 'pending',
        })
        results = self.Service.get_suggestions(user=self.alice_user)
        user_ids = [r['profile'].user_id.id for r in results]
        self.assertNotIn(self.bob_user.id, user_ids)

    def test_excludes_blocked(self):
        if 'social_safety.block' not in self.env:
            self.skipTest('social_safety not installed')
        self.env['social_safety.block'].sudo().with_user(self.alice_user).create({
            'blocker_id': self.alice_user.id,
            'blocked_id': self.bob_user.id,
        })
        results = self.Service.get_suggestions(user=self.alice_user)
        user_ids = [r['profile'].user_id.id for r in results]
        self.assertNotIn(self.bob_user.id, user_ids)

    def test_city_match_boosts_score(self):
        self.alice.city = 'Montréal'
        self.bob.city   = 'Montréal'
        # Carol's city stays empty
        results = self.Service.get_suggestions(user=self.alice_user)
        scores_by_uid = {r['profile'].user_id.id: r['score'] for r in results}
        self.assertGreater(scores_by_uid[self.bob_user.id], scores_by_uid[self.carol_user.id])

    def test_score_is_int(self):
        results = self.Service.get_suggestions(user=self.alice_user)
        for r in results:
            self.assertIsInstance(r['score'], int)
            self.assertGreaterEqual(r['score'], 0)
            self.assertLessEqual(r['score'], 100)

    def test_results_sorted_by_score_desc(self):
        # Force a divergence: same city as bob, different from carol.
        self.alice.city = 'Quebec'
        self.bob.city   = 'Quebec'
        self.carol.city = 'Other'
        results = self.Service.get_suggestions(user=self.alice_user)
        scores = [r['score'] for r in results]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_limit_respected(self):
        # Create extra candidates
        for i in range(8):
            _make_social_user(self.env, f'sug_extra_{i}')
        results = self.Service.get_suggestions(user=self.alice_user, limit=3)
        self.assertLessEqual(len(results), 3)

    def test_excludes_non_member_visibility(self):
        self.bob.visibility = 'connections'
        results = self.Service.get_suggestions(user=self.alice_user)
        user_ids = [r['profile'].user_id.id for r in results]
        self.assertNotIn(self.bob_user.id, user_ids)
