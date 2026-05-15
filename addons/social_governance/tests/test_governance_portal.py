import datetime

from odoo import fields
from odoo.exceptions import UserError
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
        cls.Proposal = cls.env['social_governance.proposal']

    def _make_proposal(self, user=None, state='draft', closes_delta=7):
        u = user or self.moderator
        p = self.Proposal.with_user(u).create({
            'name': 'Test Proposal',
            'description': '<p>Test</p>',
            'author_id': u.id,
            'category_id': self.category.id,
            'voting_closes_at': fields.Datetime.now() + datetime.timedelta(days=closes_delta),
        })
        if state == 'voting':
            p.with_user(u).action_start_voting()
        elif state == 'open':
            p.with_user(u).action_open()
        return p

    # ── Recherche / filtre ────────────────────────────────────────────────

    def test_proposals_searchable_by_state(self):
        p = self._make_proposal(state='voting')
        voting = self.Proposal.sudo().search([('state', '=', 'voting')])
        self.assertIn(p, voting)

    def test_draft_not_in_voting_filter(self):
        p = self._make_proposal(state='draft')
        voting = self.Proposal.sudo().search([('state', '=', 'voting')])
        self.assertNotIn(p, voting)

    # ── Vote ──────────────────────────────────────────────────────────────

    def test_vote_yes_recorded(self):
        p = self._make_proposal(state='voting')
        p.with_user(self.member).action_vote('yes')
        vote = self.env['social_governance.vote'].sudo().search([
            ('proposal_id', '=', p.id), ('voter_id', '=', self.member.id),
        ], limit=1)
        self.assertTrue(vote)
        self.assertEqual(vote.choice, 'yes')

    def test_vote_change(self):
        p = self._make_proposal(state='voting')
        p.with_user(self.member).action_vote('yes')
        p.with_user(self.member).action_vote('no')
        vote = self.env['social_governance.vote'].sudo().search([
            ('proposal_id', '=', p.id), ('voter_id', '=', self.member.id),
        ], limit=1)
        self.assertEqual(vote.choice, 'no')

    def test_vote_requires_voting_state(self):
        p = self._make_proposal(state='draft')
        with self.assertRaises(UserError):
            p.with_user(self.member).action_vote('yes')

    def test_approval_pct_computed(self):
        p = self._make_proposal(state='voting')
        p.with_user(self.member).action_vote('yes')
        p.with_user(self.moderator).action_vote('no')
        self.assertGreaterEqual(p.approval_pct, 0)
        self.assertLessEqual(p.approval_pct, 100)

    def test_approval_pct_all_yes(self):
        p = self._make_proposal(state='voting')
        p.with_user(self.member).action_vote('yes')
        p.with_user(self.moderator).action_vote('yes')
        self.assertEqual(p.approval_pct, 100)

    def test_abstain_not_in_decisive(self):
        p = self._make_proposal(state='voting')
        p.with_user(self.member).action_vote('abstain')
        self.assertEqual(p.approval_pct, 0)
        self.assertEqual(p.abstain_count, 1)
        self.assertEqual(p.yes_count, 0)

    # ── Retrait ───────────────────────────────────────────────────────────

    def test_author_can_withdraw(self):
        p = self._make_proposal(state='voting')
        p.with_user(self.moderator).action_withdraw()
        self.assertEqual(p.state, 'withdrawn')

    def test_moderator_can_withdraw_others(self):
        p = self._make_proposal(user=self.member, state='draft')
        p.with_user(self.moderator).action_withdraw()
        self.assertEqual(p.state, 'withdrawn')

    def test_member_cannot_withdraw_others(self):
        p = self._make_proposal(user=self.moderator, state='draft')
        with self.assertRaises(UserError):
            p.with_user(self.member).action_withdraw()

    def test_cannot_withdraw_accepted(self):
        p = self._make_proposal(state='voting')
        p.with_user(self.member).action_vote('yes')
        p.with_user(self.moderator).action_close_voting()
        with self.assertRaises(UserError):
            p.with_user(self.moderator).action_withdraw()

    # ── Clôture ───────────────────────────────────────────────────────────

    def test_close_voting_majority_accepted(self):
        p = self._make_proposal(state='voting')
        p.with_user(self.member).action_vote('yes')
        p.with_user(self.moderator).action_close_voting()
        self.assertEqual(p.state, 'accepted')

    def test_close_voting_majority_rejected(self):
        p = self._make_proposal(state='voting')
        p.with_user(self.member).action_vote('no')
        p.with_user(self.moderator).action_close_voting()
        self.assertEqual(p.state, 'rejected')

    # ── Journal ───────────────────────────────────────────────────────────

    def test_decision_log_public_only(self):
        self.env['social_governance.decision_log'].sudo().create({
            'title': 'Public Decision', 'body': '<p>public</p>',
            'moderator_id': self.moderator.id, 'category': 'other', 'is_public': True,
        })
        self.env['social_governance.decision_log'].sudo().create({
            'title': 'Private Decision', 'body': '<p>private</p>',
            'moderator_id': self.moderator.id, 'category': 'other', 'is_public': False,
        })
        public = self.env['social_governance.decision_log'].sudo().search([('is_public', '=', True)])
        self.assertFalse(public.filtered(lambda e: e.title == 'Private Decision'))


@tagged('social_governance', 'governance_portal', 'post_install', '-at_install')
class TestGovernancePortalHttp(HttpCase):

    def _setup_mod(self):
        group_social = self.env.ref('social_base.group_social_user')
        group_mod = self.env.ref('social_base.group_social_moderator')
        mod = self.env['res.users'].create({
            'name': 'GovHTTPMod', 'login': 'gov_http_mod',
            'email': 'gov_http_mod@gov.test', 'password': 'Test1234!',
            'group_ids': [(4, group_social.id), (4, group_mod.id)],
        })
        return mod

    def _make_proposal(self, user=None, state='draft'):
        u = user or self.env.ref('base.user_admin')
        category = self.env.ref('social_governance.category_other')
        p = self.env['social_governance.proposal'].with_user(u).create({
            'name': 'HTTP Test Proposal',
            'description': '<p>Test HTTP</p>',
            'author_id': u.id,
            'category_id': category.id,
            'voting_closes_at': fields.Datetime.now() + __import__('datetime').timedelta(days=7),
        })
        if state == 'voting':
            p.with_user(u).action_start_voting()
        return p

    def test_governance_unauthenticated_redirects(self):
        resp = self.url_open('/governance', allow_redirects=False)
        self.assertIn(resp.status_code, (302, 303))

    def test_governance_authenticated_ok(self):
        self.authenticate('admin', 'admin')
        resp = self.url_open('/governance')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'Gouvernance', resp.content)

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

    def test_governance_list_has_create_form(self):
        self.authenticate('admin', 'admin')
        resp = self.url_open('/governance')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'governance/create', resp.content)

    def test_create_proposal(self):
        category = self.env.ref('social_governance.category_other')
        self.authenticate('admin', 'admin')
        resp = self.url_open(
            '/governance/create',
            data={
                'csrf_token': self.csrf_token(),
                'name': 'HTTP Created Proposal',
                'description': 'Description test HTTP',
                'category_id': str(category.id),
            },
        )
        self.assertEqual(resp.status_code, 200)
        admin = self.env.ref('base.user_admin')
        p = self.env['social_governance.proposal'].sudo().search([
            ('author_id', '=', admin.id),
            ('name', '=', 'HTTP Created Proposal'),
        ], limit=1)
        self.assertTrue(p)

    def test_create_proposal_missing_fields(self):
        self.authenticate('admin', 'admin')
        resp = self.url_open(
            '/governance/create',
            data={'csrf_token': self.csrf_token(), 'name': '', 'description': '', 'category_id': ''},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'error', resp.url.encode())

    def test_detail_page_shows_proposal(self):
        p = self._make_proposal()
        self.authenticate('admin', 'admin')
        resp = self.url_open(f'/governance/{p.id}')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'HTTP Test Proposal', resp.content)

    def test_vote_on_proposal(self):
        p = self._make_proposal(state='voting')
        self.authenticate('admin', 'admin')
        resp = self.url_open(
            f'/governance/{p.id}/vote',
            data={'csrf_token': self.csrf_token(), 'choice': 'yes'},
        )
        self.assertEqual(resp.status_code, 200)
        admin = self.env.ref('base.user_admin')
        vote = self.env['social_governance.vote'].sudo().search([
            ('proposal_id', '=', p.id), ('voter_id', '=', admin.id),
        ], limit=1)
        self.assertTrue(vote)
        self.assertEqual(vote.choice, 'yes')

    def test_vote_invalid_choice_redirects_with_error(self):
        p = self._make_proposal(state='voting')
        self.authenticate('admin', 'admin')
        resp = self.url_open(
            f'/governance/{p.id}/vote',
            data={'csrf_token': self.csrf_token(), 'choice': 'invalid'},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'error', resp.url.encode())

    def test_withdraw_by_author(self):
        admin = self.env.ref('base.user_admin')
        p = self._make_proposal(user=admin, state='draft')
        self.authenticate('admin', 'admin')
        resp = self.url_open(
            f'/governance/{p.id}/withdraw',
            data={'csrf_token': self.csrf_token()},
        )
        self.assertEqual(resp.status_code, 200)
        p.invalidate_recordset()
        self.assertEqual(p.state, 'withdrawn')

    def test_withdraw_by_non_author_forbidden(self):
        mod = self._setup_mod()
        p = self._make_proposal(user=mod, state='draft')
        self.authenticate('admin', 'admin')
        resp = self.url_open(
            f'/governance/{p.id}/withdraw',
            data={'csrf_token': self.csrf_token()},
        )
        self.assertEqual(resp.status_code, 403)

    def test_detail_shows_vote_bar_when_votes(self):
        admin = self.env.ref('base.user_admin')
        p = self._make_proposal(user=admin, state='voting')
        self.env['social_governance.vote'].sudo().create({
            'proposal_id': p.id, 'voter_id': admin.id, 'choice': 'yes',
        })
        self.authenticate('admin', 'admin')
        resp = self.url_open(f'/governance/{p.id}')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'progress-bar', resp.content)
