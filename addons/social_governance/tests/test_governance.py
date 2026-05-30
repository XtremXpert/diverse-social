import datetime

from odoo import fields
from odoo.tests import TransactionCase, tagged
from odoo.exceptions import ValidationError, UserError


@tagged('social_governance', 'governance')
class TestGovernance(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        group_user = cls.env.ref('base.group_user')
        group_social = cls.env.ref('social_base.group_social_user')
        group_mod = cls.env.ref('social_base.group_social_moderator')

        def make_user(name, login, extra_groups=None):
            groups = [(4, group_user.id), (4, group_social.id)]
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

    def _future(self, days=7):
        return fields.Datetime.now() + datetime.timedelta(days=days)

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

    # ── Quorum ────────────────────────────────────────────────────────────────

    def test_close_voting_inconclusive_when_under_quorum(self):
        """A vote that doesn't reach the category's min_quorum closes as
        'inconclusive' — distinguishes 'not convincing' from 'not mobilized'
        for civic transparency."""
        self.category.min_quorum = 5
        p = self._setup_voting_proposal()
        # Only 1 vote — well under quorum of 5
        p.with_user(self.alice).action_vote('yes')
        p.action_close_voting()
        self.assertEqual(p.state, 'inconclusive')

    def test_close_voting_accepted_when_quorum_met(self):
        """At quorum exactly, normal yes/no ratio decides."""
        self.category.min_quorum = 3
        p = self._setup_voting_proposal()
        p.with_user(self.alice).action_vote('yes')
        p.with_user(self.bob).action_vote('yes')
        p.with_user(self.moderator).action_vote('no')
        p.action_close_voting()
        self.assertEqual(p.state, 'accepted')

    def test_close_voting_rejected_when_quorum_met_but_majority_no(self):
        self.category.min_quorum = 2
        p = self._setup_voting_proposal()
        p.with_user(self.alice).action_vote('no')
        p.with_user(self.bob).action_vote('no')
        p.action_close_voting()
        self.assertEqual(p.state, 'rejected')

    def test_close_voting_no_quorum_check_when_category_zero(self):
        """min_quorum=0 means quorum check disabled — legacy behaviour."""
        self.category.min_quorum = 0
        p = self._setup_voting_proposal()
        # Single yes vote → would be inconclusive with quorum, accepted without
        p.with_user(self.alice).action_vote('yes')
        p.action_close_voting()
        self.assertEqual(p.state, 'accepted')

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

    # ── my_vote computed ──────────────────────────────────────────────────────

    def test_my_vote_returns_choice(self):
        """my_vote retourne le choix de l'utilisateur courant."""
        p = self._make_proposal()
        p.sudo().write({'voting_closes_at': self._future()})
        p.action_start_voting()
        p.with_user(self.alice).action_vote('yes')
        self.assertEqual(p.with_user(self.alice).my_vote, 'yes')

    def test_my_vote_false_when_not_voted(self):
        """my_vote returns False if the user has not voted."""
        p = self._make_proposal()
        p.sudo().write({'voting_closes_at': self._future()})
        p.action_start_voting()
        self.assertFalse(p.with_user(self.bob).my_vote)

    def test_my_vote_updates_on_change(self):
        """my_vote reflects the new choice after vote change."""
        p = self._make_proposal()
        p.sudo().write({'voting_closes_at': self._future()})
        p.action_start_voting()
        p.with_user(self.alice).action_vote('yes')
        p.with_user(self.alice).action_vote('no')
        self.assertEqual(p.with_user(self.alice).my_vote, 'no')

    # ── Approbation edge cases ────────────────────────────────────────────────

    def test_approval_pct_all_abstain(self):
        """All abstentions → no decisive vote → 0%."""
        p = self._make_proposal()
        p.sudo().write({'voting_closes_at': self._future()})
        p.action_start_voting()
        p.with_user(self.alice).action_vote('abstain')
        p.with_user(self.bob).action_vote('abstain')
        self.assertEqual(p.approval_pct, 0)

    def test_approval_pct_all_yes(self):
        """Que des oui → 100%."""
        p = self._make_proposal()
        p.sudo().write({'voting_closes_at': self._future()})
        p.action_start_voting()
        p.with_user(self.alice).action_vote('yes')
        p.with_user(self.bob).action_vote('yes')
        self.assertEqual(p.approval_pct, 100)

    def test_multiple_voters_correct_counts(self):
        """Three different voters: counters are consistent."""
        p = self._make_proposal()
        p.sudo().write({'voting_closes_at': self._future()})
        p.action_start_voting()
        p.with_user(self.alice).action_vote('yes')
        p.with_user(self.bob).action_vote('no')
        p.with_user(self.moderator).action_vote('abstain')
        self.assertEqual(p.yes_count, 1)
        self.assertEqual(p.no_count, 1)
        self.assertEqual(p.abstain_count, 1)
        self.assertEqual(p.vote_count, 3)

    def test_vote_upsert_no_duplicate(self):
        """Changing your vote does not create an extra record."""
        p = self._make_proposal()
        p.sudo().write({'voting_closes_at': self._future()})
        p.action_start_voting()
        p.with_user(self.alice).action_vote('yes')
        p.with_user(self.alice).action_vote('no')
        votes = self.Vote.sudo().search([('proposal_id', '=', p.id), ('voter_id', '=', self.alice.id)])
        self.assertEqual(len(votes), 1)

    # ── Decision log ──────────────────────────────────────────────────────────

    def test_decision_log_pagination(self):
        """get_public_log supports the offset parameter."""
        for i in range(3):
            self.Log.with_user(self.moderator).create({
                'title': f'Log pagination {i}',
                'body': '<p>test</p>',
                'category': 'other',
                'decision_date': f'2026-03-{10 + i:02d}',
                'is_public': True,
            })
        page1 = self.Log.get_public_log(limit=2, offset=0)
        page2 = self.Log.get_public_log(limit=2, offset=2)
        ids1 = {r['id'] for r in page1}
        ids2 = {r['id'] for r in page2}
        self.assertEqual(len(page1), 2)
        self.assertTrue(ids1.isdisjoint(ids2))

    def test_decision_all_categories_accepted(self):
        """Each category value is accepted."""
        categories = ['ban', 'warning', 'rule_change', 'content_removal', 'dispute', 'other']
        for cat in categories:
            log = self.Log.with_user(self.moderator).create({
                'title': f'Decision {cat}',
                'body': '<p>test</p>',
                'category': cat,
                'decision_date': '2026-04-01',
            })
            self.assertEqual(log.category, cat)

    def test_implement_sets_implemented_at(self):
        """action_implement() renseigne implemented_at."""
        p = self._make_proposal()
        p.sudo().write({'voting_closes_at': self._future()})
        p.action_start_voting()
        p.with_user(self.alice).action_vote('yes')
        p.action_close_voting()
        self.assertEqual(p.state, 'accepted')
        p.action_implement()
        self.assertTrue(p.implemented_at)

    def test_cron_returns_count(self):
        """cron_close_expired_votes retourne un entier >= 0."""
        count = self.Proposal.cron_close_expired_votes()
        self.assertIsInstance(count, int)
        self.assertGreaterEqual(count, 0)
