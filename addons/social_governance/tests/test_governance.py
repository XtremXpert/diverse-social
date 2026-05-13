from odoo.tests import TransactionCase, tagged
from odoo.exceptions import ValidationError, UserError


@tagged('social_governance', 'governance')
class TestGovernance(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        group_user = cls.env.ref('social_base.group_social_user')
        group_mod = cls.env.ref('social_base.group_social_moderator')

        def make_user(name, login, extra_groups=None):
            groups = [(4, group_user.id)]
            for g in (extra_groups or []):
                groups.append((4, g.id))
            return cls.env['res.users'].create({
                'name': name, 'login': login, 'email': f'{login}@gov.test',
                'group_ids': groups,
            })

        cls.alice = make_user('Alice', 'gov_alice')
        cls.bob = make_user('Bob', 'gov_bob')
        cls.moderator = make_user('Mod', 'gov_mod', extra_groups=[group_mod])

        cls.Proposal = cls.env['social_governance.proposal']
        cls.Vote = cls.env['social_governance.vote']
        cls.Log = cls.env['social_governance.decision_log']

        cls.category = cls.env['social_governance.proposal_category'].create({
            'name': 'Test Category',
        })

    def _make_proposal(self, user=None, state='draft'):
        user = user or self.alice
        p = self.Proposal.with_user(user).create({
            'name': 'Test Proposal',
            'description': '<p>Details</p>',
            'author_id': user.id,
            'category_id': self.category.id,
        })
        return p

    # ── Proposal lifecycle ────────────────────────────────────────────────────

    def test_create_proposal(self):
        p = self._make_proposal()
        self.assertEqual(p.state, 'draft')

    def test_action_open(self):
        p = self._make_proposal()
        p.action_open()
        self.assertEqual(p.state, 'open')

    def test_action_open_only_from_draft(self):
        p = self._make_proposal()
        p.action_open()
        with self.assertRaises(UserError):
            p.action_open()

    def test_start_voting_requires_close_date(self):
        p = self._make_proposal()
        with self.assertRaises(UserError):
            p.action_start_voting()

    def test_start_voting(self):
        from odoo import fields
        p = self._make_proposal()
        p.voting_closes_at = fields.Datetime.now()
        p.action_start_voting()
        self.assertEqual(p.state, 'voting')

    def test_voting_date_constraint(self):
        from odoo import fields
        import datetime
        p = self._make_proposal()
        now = fields.Datetime.now()
        p.voting_opens_at = now + datetime.timedelta(hours=2)
        with self.assertRaises(ValidationError):
            p.voting_closes_at = now + datetime.timedelta(hours=1)
            p.flush_recordset()

    # ── Voting ────────────────────────────────────────────────────────────────

    def _setup_voting_proposal(self):
        from odoo import fields
        p = self._make_proposal()
        p.voting_closes_at = fields.Datetime.now()
        p.action_start_voting()
        return p

    def test_cast_vote_yes(self):
        p = self._setup_voting_proposal()
        p.with_user(self.alice).action_vote('yes')
        self.assertEqual(p.yes_count, 1)

    def test_cast_vote_changes(self):
        p = self._setup_voting_proposal()
        p.with_user(self.alice).action_vote('yes')
        p.with_user(self.alice).action_vote('no')
        self.assertEqual(p.yes_count, 0)
        self.assertEqual(p.no_count, 1)
        self.assertEqual(p.vote_count, 1)

    def test_vote_invalid_choice(self):
        p = self._setup_voting_proposal()
        with self.assertRaises(ValidationError):
            p.with_user(self.alice).action_vote('maybe')

    def test_vote_not_open(self):
        p = self._make_proposal()
        with self.assertRaises(UserError):
            p.with_user(self.alice).action_vote('yes')

    def test_approval_pct(self):
        p = self._setup_voting_proposal()
        p.with_user(self.alice).action_vote('yes')
        p.with_user(self.bob).action_vote('no')
        self.assertEqual(p.approval_pct, 50)

    def test_approval_pct_no_votes(self):
        p = self._setup_voting_proposal()
        self.assertEqual(p.approval_pct, 0)

    # ── Close voting ──────────────────────────────────────────────────────────

    def test_close_voting_accepted(self):
        p = self._setup_voting_proposal()
        p.with_user(self.alice).action_vote('yes')
        p.with_user(self.bob).action_vote('no')
        # alice + moderator vote yes → 2 yes vs 1 no
        p.with_user(self.moderator).action_vote('yes')
        p.action_close_voting()
        self.assertEqual(p.state, 'accepted')

    def test_close_voting_rejected(self):
        p = self._setup_voting_proposal()
        p.with_user(self.alice).action_vote('no')
        p.action_close_voting()
        self.assertEqual(p.state, 'rejected')

    def test_close_voting_only_from_voting(self):
        p = self._make_proposal()
        with self.assertRaises(UserError):
            p.action_close_voting()

    # ── Withdraw ──────────────────────────────────────────────────────────────

    def test_author_can_withdraw(self):
        p = self._make_proposal(user=self.alice)
        p.with_user(self.alice).action_withdraw()
        self.assertEqual(p.state, 'withdrawn')

    def test_non_author_cannot_withdraw(self):
        p = self._make_proposal(user=self.alice)
        with self.assertRaises(UserError):
            p.with_user(self.bob).action_withdraw()

    def test_moderator_can_withdraw(self):
        p = self._make_proposal(user=self.alice)
        p.with_user(self.moderator).action_withdraw()
        self.assertEqual(p.state, 'withdrawn')

    def test_cannot_withdraw_accepted(self):
        p = self._setup_voting_proposal()
        p.with_user(self.alice).action_vote('yes')
        p.action_close_voting()
        with self.assertRaises(UserError):
            p.with_user(self.alice).action_withdraw()

    # ── Implement ─────────────────────────────────────────────────────────────

    def test_implement_accepted(self):
        p = self._setup_voting_proposal()
        p.with_user(self.alice).action_vote('yes')
        p.action_close_voting()
        p.action_implement()
        self.assertIsNotNone(p.implemented_at)

    def test_implement_only_accepted(self):
        p = self._make_proposal()
        with self.assertRaises(UserError):
            p.action_implement()

    # ── Cron ─────────────────────────────────────────────────────────────────

    def test_cron_closes_expired(self):
        import datetime
        from odoo import fields
        p = self._make_proposal()
        past = fields.Datetime.now() - datetime.timedelta(hours=1)
        p.voting_closes_at = past
        p.action_start_voting()
        count = self.Proposal.cron_close_expired_votes()
        self.assertGreaterEqual(count, 1)
        p.invalidate_recordset()
        self.assertIn(p.state, ('accepted', 'rejected'))

    # ── Decision log ─────────────────────────────────────────────────────────

    def test_create_decision(self):
        d = self.Log.with_user(self.moderator).create({
            'title': 'Member banned',
            'body': '<p>Reason: repeated violations</p>',
            'category': 'ban',
            'decision_date': '2026-01-01',
        })
        self.assertEqual(d.category, 'ban')
        self.assertTrue(d.is_public)

    def test_decision_get_public_log(self):
        self.Log.with_user(self.moderator).create({
            'title': 'Public decision',
            'body': '<p>Public</p>',
            'category': 'other',
            'decision_date': '2026-02-01',
            'is_public': True,
        })
        self.Log.with_user(self.moderator).create({
            'title': 'Private decision',
            'body': '<p>Private</p>',
            'category': 'other',
            'decision_date': '2026-02-02',
            'is_public': False,
        })
        public = self.Log.get_public_log()
        titles = [r['title'] for r in public]
        self.assertIn('Public decision', titles)
        self.assertNotIn('Private decision', titles)
