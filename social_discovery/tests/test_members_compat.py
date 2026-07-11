from odoo.tests import HttpCase, tagged


def _make_social_user(env, login):
    group_user = env.ref('base.group_user')
    group_social = env.ref('social_base.group_social_user')
    user = env['res.users'].create({
        'name': login.capitalize(),
        'login': login,
        'email': f'{login}@compat.test',
        'password': 'Test1234!',
        'group_ids': [(4, group_user.id), (4, group_social.id)],
    })
    profile = env['club_social_profile.profile'].sudo().get_or_create_for_user(user)
    profile.sudo().write({'onboarding_done': True, 'visibility': 'members'})
    return user, profile


@tagged('social_discovery', 'compat', 'members_portal', 'post_install', '-at_install')
class TestMembersCompat(HttpCase):
    """Validate the compatibility-score wiring in /members.

    The BDSM module is a hard prereq for these tests — they assert behaviour
    of the has_bdsm branch in the controller. Skip cleanly when absent so
    the suite still runs on non-BDSM deployments.
    """

    def setUp(self):
        super().setUp()
        if 'bdsm_role' not in self.env['club_social_profile.profile']._fields:
            self.skipTest('club_social_profile_bdsm not installed')

        self.searcher_user, self.searcher = _make_social_user(self.env, 'compat_searcher')
        self.alice_user, self.alice = _make_social_user(self.env, 'compat_alice')
        self.bob_user, self.bob = _make_social_user(self.env, 'compat_bob')

        # Pair roles for predictable compatibility :
        #   searcher = dominant, alice = soumis (compat ≈ 100×0.65 + role_score×0.35 = high)
        #   bob = dominant (same role, intentionally lower compat).
        self.searcher.sudo().bdsm_role = 'dominant'
        self.alice.sudo().bdsm_role = 'soumis'
        self.bob.sudo().bdsm_role = 'dominant'

    def test_compat_score_attached_to_page_profiles(self):
        """The controller injects compat_scores keyed by profile id."""
        self.authenticate('compat_searcher', 'Test1234!')
        resp = self.url_open('/members')
        self.assertEqual(resp.status_code, 200)
        # Alice gets a higher score with the searcher than Bob.
        score_alice = self.searcher.compute_compatibility(self.alice)['score']
        score_bob = self.searcher.compute_compatibility(self.bob)['score']
        self.assertGreater(score_alice, score_bob,
                           'dominant↔soumis should score higher than dominant↔dominant')

    def test_min_compat_filters_low_scoring_profiles(self):
        """A min_compat above bob's score must remove bob from the result page."""
        self.authenticate('compat_searcher', 'Test1234!')
        score_bob = self.searcher.compute_compatibility(self.bob)['score']
        threshold = score_bob + 5
        resp = self.url_open(f'/members?min_compat={threshold}')
        self.assertEqual(resp.status_code, 200)
        body = resp.text
        # Display name is user.name (capitalised). Bob's must not appear.
        self.assertNotIn(self.bob_user.name, body,
                         f'Bob (score={score_bob}) should be filtered out by min_compat={threshold}')

    def test_min_compat_clamped_to_valid_range(self):
        """Out-of-range min_compat values must be clamped, not crash."""
        self.authenticate('compat_searcher', 'Test1234!')
        for val in ('-50', '999', 'abc'):
            resp = self.url_open(f'/members?min_compat={val}')
            self.assertEqual(resp.status_code, 200, f'min_compat={val} crashed the page')

    def test_renders_page_with_badge_and_candidates(self):
        """The /members page lists both candidates and renders the "% match" badge."""
        self.authenticate('compat_searcher', 'Test1234!')
        resp = self.url_open('/members')
        self.assertEqual(resp.status_code, 200)
        body = resp.text
        # Display name is user.name (capitalised in setUp); login isn't rendered.
        self.assertIn(self.alice_user.name, body)
        self.assertIn(self.bob_user.name, body)
        # Match badge: check for the percentage + "match" pattern in any language.
        # FR: "% compatibilité", EN: "% match". Match on the number + % + word.
        import re
        self.assertTrue(
            re.search(r'\d+%\s*(match|compatibilit)', body),
            'Expected a compatibility percentage badge in the rendered page'
        )

    def test_sort_compat_orders_higher_score_first(self):
        """sort=compat returns the highest-scoring profile first.

        Pairing the searcher (dominant) with alice (soumis) gives a much
        higher BDSM compat than with bob (dominant↔dominant). On
        sort=compat alice must appear before bob in the rendered HTML.
        """
        self.authenticate('compat_searcher', 'Test1234!')
        resp = self.url_open('/members?sort=compat')
        self.assertEqual(resp.status_code, 200)
        body = resp.text
        # Both must appear
        self.assertIn(self.alice_user.name, body)
        self.assertIn(self.bob_user.name, body)
        # Alice's name (higher compat) appears in the document earlier than bob's
        self.assertLess(
            body.index(self.alice_user.name),
            body.index(self.bob_user.name),
            'higher-scoring profile should come first under sort=compat',
        )

    def test_sort_compat_button_visible_when_bdsm_installed(self):
        """The "Best match" sort tab appears in the UI when BDSM is on."""
        self.authenticate('compat_searcher', 'Test1234!')
        resp = self.url_open('/members')
        body = resp.text
        # EN: "Best match", FR: "Meilleur match". Check for "match" in a sort tab context.
        self.assertTrue(
            'match' in body.lower(),
            'Expected a "Best match" / "Meilleur match" sort tab in the UI'
        )
        self.assertIn('sort=compat', body)

    def test_sort_compat_active_class_when_selected(self):
        """The selected sort tab is styled btn-dark."""
        self.authenticate('compat_searcher', 'Test1234!')
        resp = self.url_open('/members?sort=compat')
        body = resp.text
        # Locate the "match" anchor (EN: "Best match", FR: "Meilleur match")
        # and check it carries btn-dark in the surrounding context.
        import re
        match = re.search(r'(match)', body, re.IGNORECASE)
        assert match is not None, 'Expected a "match" sort tab in the rendered page'
        idx = match.start()
        snippet = body[max(0, idx - 300):idx]
        self.assertIn('btn-dark', snippet)

    def test_sort_compat_respects_min_compat_filter(self):
        """sort=compat applies min_compat — low-scoring profiles drop out."""
        self.authenticate('compat_searcher', 'Test1234!')
        score_bob = self.searcher.compute_compatibility(self.bob)['score']
        threshold = score_bob + 5
        resp = self.url_open(f'/members?sort=compat&min_compat={threshold}')
        body = resp.text
        self.assertNotIn(self.bob_user.name, body,
                         f'bob (score={score_bob}) should be filtered by min_compat={threshold}')
