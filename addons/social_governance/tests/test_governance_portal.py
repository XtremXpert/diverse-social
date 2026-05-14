import datetime

from odoo import fields
from odoo.tests import HttpCase, TransactionCase, tagged


def _make_social_user(env, name, login, moderator=False):
    group_social = env.ref('social_base.group_social_user')
    group_ids = [(4, group_social.id)]
    if moderator:
        group_ids.append((4, env.ref('social_base.group_social_moderator').id))
    return env['res.users'].create({
        'name': name, 'login': login, 'email': f'{login}@gov.test',
        'password': 'Test1234!',
        'group_ids': group_ids,
    })


@tagged('social_governance', 'governance_portal')
class TestGovernancePortalData(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.moderator = _make_social_user(cls.env, 'GovMod', 'gov_mod', moderator=True)
        cls.member = _make_social_user(cls.env, 'GovMember', 'gov_member')
        cls.category = cls.env.ref('social_governance.category_other')
        cls.proposal = cls.env['social_governance.proposal'].with_user(cls.moderator).create({
            'name': 'Portal Test Proposal',
            'description': '<p>Test</p>',
            'author_id': cls.moderator.id,
            'category_id': cls.category.id,
            'voting_closes_at': fields.Datetime.now() + datetime.timedelta(days=7),
        })

    def test_proposals_searchable_by_state(self):
        self.proposal.with_user(self.moderator).action_start_voting()
        voting = self.env['social_governance.proposal'].sudo().search([
            ('state', '=', 'voting'),
        ])
        self.assertIn(self.proposal, voting)

    def test_vote_yes_recorded(self):
        self.proposal.with_user(self.moderator).action_start_voting()
        self.proposal.with_user(self.member).action_vote('yes')
        vote = self.env['social_governance.vote'].sudo().search([
            ('proposal_id', '=', self.proposal.id),
            ('voter_id', '=', self.member.id),
        ], limit=1)
        self.assertTrue(vote)
        self.assertEqual(vote.choice, 'yes')

    def test_vote_change(self):
        if self.proposal.state != 'voting':
            self.proposal.with_user(self.moderator).action_start_voting()
        self.proposal.with_user(self.member).action_vote('yes')
        self.proposal.with_user(self.member).action_vote('no')
        vote = self.env['social_governance.vote'].sudo().search([
            ('proposal_id', '=', self.proposal.id),
            ('voter_id', '=', self.member.id),
        ], limit=1)
        self.assertEqual(vote.choice, 'no')

    def test_vote_requires_voting_state(self):
        from odoo.exceptions import UserError
        draft_proposal = self.env['social_governance.proposal'].with_user(self.moderator).create({
            'name': 'Draft Portal', 'description': '<p>x</p>',
            'author_id': self.moderator.id, 'category_id': self.category.id,
            'voting_closes_at': fields.Datetime.now() + datetime.timedelta(days=7),
        })
        with self.assertRaises(UserError):
            draft_proposal.with_user(self.member).action_vote('yes')

    def test_decision_log_public_only(self):
        self.env['social_governance.decision_log'].sudo().create({
            'title': 'Public Decision', 'body': '<p>public</p>',
            'moderator_id': self.moderator.id, 'category': 'other', 'is_public': True,
        })
        self.env['social_governance.decision_log'].sudo().create({
            'title': 'Private Decision', 'body': '<p>private</p>',
            'moderator_id': self.moderator.id, 'category': 'other', 'is_public': False,
        })
        public = self.env['social_governance.decision_log'].sudo().search([
            ('is_public', '=', True),
        ])
        private_in_public = public.filtered(lambda e: e.title == 'Private Decision')
        self.assertFalse(private_in_public)

    def test_approval_pct_computed(self):
        if self.proposal.state != 'voting':
            self.proposal.with_user(self.moderator).action_start_voting()
        self.proposal.with_user(self.member).action_vote('yes')
        self.proposal.with_user(self.moderator).action_vote('no')
        self.assertGreaterEqual(self.proposal.approval_pct, 0)
        self.assertLessEqual(self.proposal.approval_pct, 100)


@tagged('social_governance', 'governance_portal', 'post_install', '-at_install')
class TestGovernancePortalHttp(HttpCase):

    def test_governance_unauthenticated_redirects(self):
        resp = self.url_open('/governance', allow_redirects=False)
        self.assertIn(resp.status_code, (302, 303))

    def test_governance_authenticated_ok(self):
        self.authenticate('admin', 'admin')
        resp = self.url_open('/governance')
        self.assertEqual(resp.status_code, 200)

    def test_governance_log_authenticated_ok(self):
        self.authenticate('admin', 'admin')
        resp = self.url_open('/governance/log')
        self.assertEqual(resp.status_code, 200)

    def test_governance_state_filter(self):
        self.authenticate('admin', 'admin')
        for state in ('draft', 'open', 'voting', 'accepted', 'rejected'):
            resp = self.url_open(f'/governance?state={state}')
            self.assertEqual(resp.status_code, 200)

    def test_governance_detail_not_found(self):
        self.authenticate('admin', 'admin')
        resp = self.url_open('/governance/999999')
        self.assertEqual(resp.status_code, 404)
