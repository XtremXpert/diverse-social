from odoo.tests import TransactionCase, tagged


@tagged('club_social_profile_bdsm', 'bdsm')
class TestBdsmProfile(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        group_user = cls.env.ref('base.group_user')
        group_social = cls.env.ref('social_base.group_social_user')
        cls.user1 = cls.env['res.users'].create({
            'name': 'BDSM User 1', 'login': 'bdsm_user1', 'email': 'bdsm1@test.test',
            'group_ids': [(4, group_user.id), (4, group_social.id)],
        })
        cls.user2 = cls.env['res.users'].create({
            'name': 'BDSM User 2', 'login': 'bdsm_user2', 'email': 'bdsm2@test.test',
            'group_ids': [(4, group_user.id), (4, group_social.id)],
        })
        cls.Profile = cls.env['club_social_profile.profile']
        cls.Kink = cls.env['club_social_profile_bdsm.kink']
        cls.KinkLevel = cls.env['club_social_profile_bdsm.kink_level']

    def _make_profile(self, user, role=None):
        p = self.Profile.get_or_create_for_user(user)
        if role:
            p.bdsm_role = role
        return p

    def _make_kink(self, name):
        return self.Kink.create({'name': name})

    def test_bdsm_fields_on_profile(self):
        p = self._make_profile(self.user1, role='dominant')
        self.assertEqual(p.bdsm_role, 'dominant')

    def test_kink_level_assigned(self):
        p = self._make_profile(self.user1)
        kink = self._make_kink('Bondage')
        kl = self.KinkLevel.create({
            'profile_id': p.id, 'kink_id': kink.id, 'level': 'oui',
        })
        self.assertIn(kl, p.kink_level_ids)

    def test_kink_level_unique(self):
        from odoo.exceptions import ValidationError
        p = self._make_profile(self.user1)
        kink = self._make_kink('Wax')
        self.KinkLevel.create({'profile_id': p.id, 'kink_id': kink.id, 'level': 'curieux'})
        with self.assertRaises(Exception):
            self.KinkLevel.create({'profile_id': p.id, 'kink_id': kink.id, 'level': 'oui'})

    def test_role_compat_dominant_soumis(self):
        p1 = self._make_profile(self.user1, role='dominant')
        p2 = self._make_profile(self.user2, role='soumis')
        result = p1.compute_compatibility(p2)
        self.assertEqual(result['role_score'], 100)

    def test_role_compat_same_role_not_switch(self):
        p1 = self._make_profile(self.user1, role='dominant')
        p2 = self._make_profile(self.user2, role='dominant')
        result = p1.compute_compatibility(p2)
        self.assertEqual(result['role_score'], 30)

    def test_compatibility_shared_kinks(self):
        p1 = self._make_profile(self.user1, role='dominant')
        p2 = self._make_profile(self.user2, role='soumis')
        kink1 = self._make_kink('Rope')
        kink2 = self._make_kink('Impact')
        for p in [p1, p2]:
            self.KinkLevel.create({'profile_id': p.id, 'kink_id': kink1.id, 'level': 'oui'})
        self.KinkLevel.create({'profile_id': p1.id, 'kink_id': kink2.id, 'level': 'soft'})

        result = p1.compute_compatibility(p2)
        self.assertEqual(result['shared_count'], 1)
        self.assertIn('Rope', result['shared_kinks'])
        self.assertGreater(result['score'], 0)

    def test_kink_request_approve(self):
        req = self.env['club_social_profile_bdsm.kink_request'].create({
            'name': 'New Kink', 'requester_id': self.user1.id,
        })
        req.action_approve()
        self.assertEqual(req.state, 'approved')
        self.assertTrue(req.kink_id)
        self.assertEqual(req.kink_id.name, 'New Kink')

    def test_kink_request_approve_deduplicates(self):
        existing = self._make_kink('Existing Kink')
        req = self.env['club_social_profile_bdsm.kink_request'].create({
            'name': 'existing kink', 'requester_id': self.user1.id,
        })
        req.action_approve()
        self.assertEqual(req.kink_id, existing)

    def test_kink_request_reject_without_reason_raises(self):
        from odoo.exceptions import ValidationError
        req = self.env['club_social_profile_bdsm.kink_request'].create({
            'name': 'Kink To Reject', 'requester_id': self.user1.id,
        })
        with self.assertRaises(ValidationError):
            req.action_reject()

    def test_kink_request_reject_with_reason_succeeds(self):
        req = self.env['club_social_profile_bdsm.kink_request'].create({
            'name': 'Kink Rejected', 'requester_id': self.user1.id,
        })
        req.write({'rejection_reason': 'Already exists under another name'})
        req.action_reject()
        self.assertEqual(req.state, 'rejected')
        self.assertTrue(req.processed_by)

    def test_kink_request_approve_sets_processed_by(self):
        req = self.env['club_social_profile_bdsm.kink_request'].create({
            'name': 'Kink Approved Processor', 'requester_id': self.user1.id,
        })
        req.action_approve()
        self.assertTrue(req.processed_by)

    def test_profile_count_increments(self):
        """profile_count on kink increments when a kink_level is added."""
        p1 = self._make_profile(self.user1)
        p2 = self._make_profile(self.user2)
        kink = self._make_kink('Count Test Kink')
        before = kink.profile_count
        self.KinkLevel.create({'profile_id': p1.id, 'kink_id': kink.id, 'level': 'oui'})
        self.KinkLevel.create({'profile_id': p2.id, 'kink_id': kink.id, 'level': 'soft'})
        kink.invalidate_recordset()
        self.assertEqual(kink.profile_count, before + 2)

    def test_role_compat_none_roles_returns_50(self):
        p1 = self._make_profile(self.user1)
        result = p1._role_compat_score(None, None)
        self.assertEqual(result, 50)

    def test_role_compat_switch_switch_returns_70(self):
        p1 = self._make_profile(self.user1)
        result = p1._role_compat_score('switch', 'switch')
        self.assertEqual(result, 70)

    def test_role_compat_sadique_masochiste(self):
        p1 = self._make_profile(self.user1)
        result = p1._role_compat_score('sadique', 'masochiste')
        self.assertEqual(result, 100)

    def test_role_compat_maitre_esclave(self):
        p1 = self._make_profile(self.user1)
        result = p1._role_compat_score('maitre', 'esclave')
        self.assertEqual(result, 100)

    def test_role_compat_unknown_pair_returns_40(self):
        p1 = self._make_profile(self.user1)
        result = p1._role_compat_score('spectateur', 'curieux')
        self.assertEqual(result, 40)

    def test_compatibility_no_kinks_kink_score_50(self):
        """With no kinks on either side, kink_score must be 50."""
        p1 = self._make_profile(self.user1)
        p2 = self._make_profile(self.user2)
        result = p1.compute_compatibility(p2)
        self.assertEqual(result['kink_score'], 50)

    def test_compatibility_total_score_formula(self):
        """score = round(kink_score * 0.65 + role_score * 0.35)."""
        p1 = self._make_profile(self.user1, role='dominant')
        p2 = self._make_profile(self.user2, role='soumis')
        result = p1.compute_compatibility(p2)
        expected = round(result['kink_score'] * 0.65 + result['role_score'] * 0.35)
        self.assertEqual(result['score'], expected)
