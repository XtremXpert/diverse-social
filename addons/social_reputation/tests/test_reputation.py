from odoo.tests import TransactionCase, tagged
from odoo.exceptions import ValidationError, UserError


@tagged('social_reputation', 'reputation')
class TestReputation(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        group_user = cls.env.ref('social_base.group_social_user')

        def make_user(name, login, email):
            return cls.env['res.users'].create({
                'name': name, 'login': login, 'email': email,
                'group_ids': [(4, group_user.id)],
            })

        cls.alice = make_user('Alice', 'rep_alice', 'alice@rep.test')
        cls.bob = make_user('Bob', 'rep_bob', 'bob@rep.test')
        cls.carol = make_user('Carol', 'rep_carol', 'carol@rep.test')
        cls.dave = make_user('Dave', 'rep_dave', 'dave@rep.test')

        Profile = cls.env['club_social_profile.profile']
        cls.alice_p = Profile.get_or_create_for_user(cls.alice)
        cls.bob_p = Profile.get_or_create_for_user(cls.bob)
        cls.carol_p = Profile.get_or_create_for_user(cls.carol)
        cls.dave_p = Profile.get_or_create_for_user(cls.dave)

        cls.Vouching = cls.env['social_reputation.vouching']

    # ── Basic vouching ────────────────────────────────────────────────────────

    def test_vouch_creates_record(self):
        v = self.Vouching.with_user(self.alice).vouch_for(self.bob, statement='Great person')
        self.assertEqual(v.sponsor_id, self.alice)
        self.assertEqual(v.newcomer_id, self.bob)
        self.assertEqual(v.state, 'active')

    def test_cannot_vouch_self(self):
        with self.assertRaises(ValidationError):
            self.Vouching.with_user(self.alice).create({
                'sponsor_id': self.alice.id,
                'newcomer_id': self.alice.id,
            })

    def test_duplicate_vouching_raises(self):
        self.Vouching.with_user(self.alice).vouch_for(self.bob)
        with self.assertRaises(UserError):
            self.Vouching.with_user(self.alice).vouch_for(self.bob)

    def test_circular_vouching_raises(self):
        self.Vouching.with_user(self.alice).vouch_for(self.bob)
        with self.assertRaises(ValidationError):
            self.Vouching.with_user(self.bob).vouch_for(self.alice)

    # ── Withdraw ──────────────────────────────────────────────────────────────

    def test_withdraw_requires_reason(self):
        v = self.Vouching.with_user(self.alice).vouch_for(self.carol)
        with self.assertRaises(UserError):
            v.with_user(self.alice).action_withdraw(reason=None)

    def test_withdraw_sets_state(self):
        v = self.Vouching.with_user(self.alice).vouch_for(self.carol)
        v.with_user(self.alice).action_withdraw(reason='Changed my mind')
        self.assertEqual(v.state, 'withdrawn')
        self.assertTrue(v.withdrawn_at)

    def test_withdraw_only_sponsor_or_moderator(self):
        v = self.Vouching.with_user(self.alice).vouch_for(self.carol)
        with self.assertRaises(UserError):
            v.with_user(self.bob).action_withdraw(reason='Not my vouching')

    def test_withdraw_already_withdrawn_raises(self):
        v = self.Vouching.with_user(self.alice).vouch_for(self.carol)
        v.with_user(self.alice).action_withdraw(reason='First withdrawal')
        with self.assertRaises(UserError):
            v.with_user(self.alice).action_withdraw(reason='Second withdrawal')

    def test_withdrawn_vouching_blocks_new_one(self):
        v = self.Vouching.with_user(self.alice).vouch_for(self.carol)
        v.with_user(self.alice).action_withdraw(reason='Withdrawn')
        with self.assertRaises(UserError):
            self.Vouching.with_user(self.alice).vouch_for(self.carol)

    # ── Profile extension ─────────────────────────────────────────────────────

    def test_is_vouched_after_vouching(self):
        self.Vouching.with_user(self.alice).vouch_for(self.dave)
        self.dave_p.invalidate_recordset()
        self.assertTrue(self.dave_p.is_vouched)
        self.assertEqual(self.dave_p.vouching_received_count, 1)

    def test_is_not_vouched_without_vouching(self):
        self.assertFalse(self.carol_p.is_vouched)

    def test_sponsor_ids_computed(self):
        self.Vouching.with_user(self.alice).vouch_for(self.dave)
        self.Vouching.with_user(self.bob).vouch_for(self.dave)
        self.dave_p.invalidate_recordset()
        self.assertIn(self.alice, self.dave_p.sponsor_ids)
        self.assertIn(self.bob, self.dave_p.sponsor_ids)

    def test_vouching_given_count(self):
        self.Vouching.with_user(self.alice).vouch_for(self.dave)
        self.alice_p.invalidate_recordset()
        self.assertEqual(self.alice_p.vouching_given_count, 1)

    def test_profile_action_vouch(self):
        self.dave_p.with_user(self.alice).action_vouch(statement='Trusted')
        self.dave_p.invalidate_recordset()
        self.assertTrue(self.dave_p.is_vouched)

    def test_profile_action_withdraw_vouching(self):
        self.dave_p.with_user(self.alice).action_vouch(statement='Trusted')
        self.dave_p.with_user(self.alice).action_withdraw_vouching(reason='Changed my mind')
        self.dave_p.invalidate_recordset()
        self.assertFalse(self.dave_p.is_vouched)

    def test_withdraw_vouching_when_not_vouched_raises(self):
        with self.assertRaises(UserError):
            self.carol_p.with_user(self.alice).action_withdraw_vouching(reason='Never vouched')

    # ── Vouching chain ────────────────────────────────────────────────────────

    def test_vouching_chain_depth_1(self):
        self.Vouching.with_user(self.alice).vouch_for(self.dave)
        chain = self.dave_p.get_vouching_chain(depth=1)
        self.assertEqual(len(chain), 1)
        self.assertIn(self.alice, chain[0])

    def test_vouching_chain_depth_2(self):
        # alice → dave → carol chain
        self.Vouching.with_user(self.alice).vouch_for(self.dave)
        self.Vouching.with_user(self.dave).vouch_for(self.carol)
        chain = self.carol_p.get_vouching_chain(depth=2)
        self.assertGreaterEqual(len(chain), 1)
        level_0_users = chain[0]
        self.assertIn(self.dave, level_0_users)

    # ── Discovery filter ──────────────────────────────────────────────────────

    def test_discovery_require_vouched(self):
        self.alice_p.write({'visibility': 'members'})
        self.bob_p.write({'visibility': 'members'})
        self.Vouching.with_user(self.alice).vouch_for(self.bob)
        self.bob_p.invalidate_recordset()

        crit = self.env['social_discovery.criteria'].create({
            'profile_id': self.carol_p.id,
            'name': 'Vouched only',
            'require_vouched': True,
        })
        profiles = crit._find_profiles()
        self.assertIn(self.bob_p, profiles)
        self.assertNotIn(self.alice_p, profiles)  # alice has no sponsor
