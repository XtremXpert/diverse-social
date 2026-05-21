from odoo.http import Request
from odoo.tests import HttpCase, TransactionCase, tagged
from odoo.exceptions import UserError


def _make_social_user(env, name, login):
    group_social = env.ref('social_base.group_social_user')
    return env['res.users'].create({
        'name': name, 'login': login, 'email': f'{login}@rep.test',
        'password': 'Test1234!',
        'group_ids': [(4, group_social.id)],
    })


def _connect(env, user_a, user_b):
    env['club_social_profile.connection'].sudo().create([
        {'user_id': user_a.id, 'connected_user_id': user_b.id, 'state': 'accepted'},
        {'user_id': user_b.id, 'connected_user_id': user_a.id, 'state': 'accepted'},
    ])


@tagged('social_reputation', 'portal_reputation')
class TestPortalReputationData(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.sponsor = _make_social_user(cls.env, 'RepSponsor', 'rep_sponsor')
        cls.newcomer = _make_social_user(cls.env, 'RepNewcomer', 'rep_newcomer')
        cls.other = _make_social_user(cls.env, 'RepOther', 'rep_other')
        _connect(cls.env, cls.sponsor, cls.newcomer)
        cls.Vouching = cls.env['social_reputation.vouching']

    def _vouch(self, sponsor=None, newcomer=None, statement='Test statement'):
        s = sponsor or self.sponsor
        n = newcomer or self.newcomer
        return self.Vouching.sudo().with_user(s).vouch_for(n, statement=statement)

    # ── Parrainer ─────────────────────────────────────────────────────────

    def test_vouch_for_connection(self):
        v = self._vouch()
        self.assertEqual(v.sponsor_id, self.sponsor)
        self.assertEqual(v.newcomer_id, self.newcomer)
        self.assertEqual(v.state, 'active')

    def test_vouch_model_allows_without_connection(self):
        # La vérification connexion est dans le contrôleur portail, pas le modèle
        v = self.Vouching.sudo().with_user(self.sponsor).vouch_for(self.other)
        self.assertEqual(v.sponsor_id, self.sponsor)

    def test_cannot_vouch_self(self):
        from odoo.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            self.Vouching.sudo().create({
                'sponsor_id': self.sponsor.id,
                'newcomer_id': self.sponsor.id,
            })

    def test_cannot_vouch_twice(self):
        self._vouch()
        with self.assertRaises(UserError):
            self._vouch()

    def test_circular_vouching_blocked(self):
        self._vouch()
        from odoo.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            self.Vouching.sudo().with_user(self.newcomer).vouch_for(self.sponsor)

    # ── Retrait ───────────────────────────────────────────────────────────

    def test_withdraw_requires_reason(self):
        v = self._vouch()
        with self.assertRaises(UserError):
            v.with_user(self.sponsor).action_withdraw(reason=None)

    def test_withdraw_sets_withdrawn(self):
        v = self._vouch()
        v.with_user(self.sponsor).action_withdraw(reason='Changed my mind')
        self.assertEqual(v.state, 'withdrawn')
        self.assertTrue(v.withdrawn_at)

    def test_withdraw_only_sponsor(self):
        v = self._vouch()
        with self.assertRaises(UserError):
            v.with_user(self.newcomer).action_withdraw(reason='Not my vouching')

    # ── Chaîne ────────────────────────────────────────────────────────────

    def test_vouching_chain_single_level(self):
        third = _make_social_user(self.env, 'ChainThird', 'rep_chain_third')
        _connect(self.env, self.newcomer, third)
        self._vouch()
        self.Vouching.sudo().with_user(self.newcomer).vouch_for(third)
        profile = self.env['club_social_profile.profile'].sudo().get_or_create_for_user(third)
        chain = profile.get_vouching_chain(depth=2)
        self.assertGreaterEqual(len(chain), 1)
        self.assertIn(self.newcomer, chain[0])

    def test_vouching_chain_empty_no_sponsor(self):
        profile = self.env['club_social_profile.profile'].sudo().get_or_create_for_user(self.other)
        chain = profile.get_vouching_chain(depth=3)
        self.assertEqual(chain, [])

    # ── Profil étendu ─────────────────────────────────────────────────────

    def test_is_vouched_after_vouch(self):
        self._vouch()
        profile = self.env['club_social_profile.profile'].sudo().get_or_create_for_user(self.newcomer)
        profile.invalidate_recordset()
        self.assertTrue(profile.is_vouched)
        self.assertEqual(profile.vouching_received_count, 1)

    def test_given_count(self):
        self._vouch()
        profile = self.env['club_social_profile.profile'].sudo().get_or_create_for_user(self.sponsor)
        profile.invalidate_recordset()
        self.assertEqual(profile.vouching_given_count, 1)

    def test_vouchable_excludes_already_vouched(self):
        self._vouch()
        from odoo.addons.social_reputation.controllers.portal import _get_user_connections
        Connection = self.env['club_social_profile.connection'].sudo()
        sent = Connection.search([('user_id', '=', self.sponsor.id), ('state', '=', 'accepted')])
        recv = Connection.search([('connected_user_id', '=', self.sponsor.id), ('state', '=', 'accepted')])
        conn_ids = set(sent.mapped('connected_user_id.id')) | set(recv.mapped('user_id.id'))
        given = self.Vouching.sudo().search([
            ('sponsor_id', '=', self.sponsor.id), ('state', '=', 'active')
        ])
        already_ids = set(given.mapped('newcomer_id.id'))
        vouchable_ids = conn_ids - already_ids
        self.assertNotIn(self.newcomer.id, vouchable_ids)


@tagged('social_reputation', 'portal_reputation', 'post_install', '-at_install')
class TestPortalReputationHttp(HttpCase):

    def _setup(self):
        group_social = self.env.ref('social_base.group_social_user')
        newcomer = self.env['res.users'].create({
            'name': 'RepHTTPNewcomer', 'login': 'rep_http_newcomer',
            'email': 'rep_http_newcomer@rep.test', 'password': 'Test1234!',
            'group_ids': [(4, group_social.id)],
        })
        admin = self.env.ref('base.user_admin')
        group_social = self.env.ref('social_base.group_social_user')
        admin.sudo().write({'group_ids': [(4, group_social.id)]})
        self.env['club_social_profile.connection'].sudo().create([
            {'user_id': admin.id, 'connected_user_id': newcomer.id, 'state': 'accepted'},
            {'user_id': newcomer.id, 'connected_user_id': admin.id, 'state': 'accepted'},
        ])
        self.env['club_social_profile.profile'].sudo().get_or_create_for_user(newcomer)
        self.env['club_social_profile.profile'].sudo().get_or_create_for_user(admin)
        return newcomer

    def test_vouching_page_unauthenticated_redirects(self):
        resp = self.url_open('/my/vouching', allow_redirects=False)
        self.assertIn(resp.status_code, (302, 303))

    def test_vouching_page_authenticated_ok(self):
        self.authenticate('admin', 'admin')
        _csrf = Request.csrf_token(self)
        resp = self.url_open('/my/vouching')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'Parrainages', resp.content)

    def test_vouching_page_has_form_for_connections(self):
        self._setup()
        self.authenticate('admin', 'admin')
        _csrf = Request.csrf_token(self)
        resp = self.url_open('/my/vouching')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'vouching/give', resp.content)

    def test_give_vouching(self):
        newcomer = self._setup()
        self.authenticate('admin', 'admin')
        _csrf = Request.csrf_token(self)
        resp = self.url_open(
            '/my/vouching/give',
            data={'csrf_token': _csrf, 
                'newcomer_id': str(newcomer.id),
                'statement': 'Great person',
            },
        )
        self.assertEqual(resp.status_code, 200)
        admin = self.env.ref('base.user_admin')
        v = self.env['social_reputation.vouching'].sudo().search([
            ('sponsor_id', '=', admin.id),
            ('newcomer_id', '=', newcomer.id),
            ('state', '=', 'active'),
        ], limit=1)
        self.assertTrue(v)
        self.assertEqual(v.statement, 'Great person')

    def test_give_vouching_non_connection_rejected(self):
        stranger = self.env['res.users'].sudo().create({
            'name': 'Stranger', 'login': 'rep_stranger',
            'email': 'rep_stranger@rep.test', 'password': 'Test1234!',
        })
        self.authenticate('admin', 'admin')
        _csrf = Request.csrf_token(self)
        self.url_open(
            '/my/vouching/give',
            data={'csrf_token': _csrf, 'newcomer_id': str(stranger.id)},
        )
        admin = self.env.ref('base.user_admin')
        v = self.env['social_reputation.vouching'].sudo().search([
            ('sponsor_id', '=', admin.id), ('newcomer_id', '=', stranger.id),
        ], limit=1)
        self.assertFalse(v)

    def test_withdraw_vouching(self):
        newcomer = self._setup()
        admin = self.env.ref('base.user_admin')
        v = self.env['social_reputation.vouching'].sudo().create({
            'sponsor_id': admin.id,
            'newcomer_id': newcomer.id,
            'statement': 'To be withdrawn',
        })
        self.authenticate('admin', 'admin')
        _csrf = Request.csrf_token(self)
        resp = self.url_open(
            f'/my/vouching/{v.id}/withdraw',
            data={'csrf_token': _csrf, 'reason': 'Test withdrawal'},
        )
        self.assertEqual(resp.status_code, 200)
        v.invalidate_recordset()
        self.assertEqual(v.state, 'withdrawn')

    def test_profile_page_has_vouch_button(self):
        newcomer = self._setup()
        self.authenticate('admin', 'admin')
        _csrf = Request.csrf_token(self)
        resp = self.url_open(f'/profile/{newcomer.id}')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'Parrainer', resp.content)

    def test_stats_show_counts(self):
        newcomer = self._setup()
        admin = self.env.ref('base.user_admin')
        self.env['social_reputation.vouching'].sudo().create({
            'sponsor_id': admin.id,
            'newcomer_id': newcomer.id,
        })
        self.authenticate('admin', 'admin')
        _csrf = Request.csrf_token(self)
        resp = self.url_open('/my/vouching')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'Personnes parrain', resp.content)

    def test_circular_vouch_does_not_leak_into_db(self):
        """If B has vouched A, A vouching B must raise ValidationError AND
        the partial INSERT must be rolled back. Without a savepoint around
        the controller's create call, the row stayed committed despite the
        constraint firing."""
        newcomer = self._setup()
        admin = self.env.ref('base.user_admin')
        Vouching = self.env['social_reputation.vouching'].sudo()
        # newcomer vouches admin first
        Vouching.create({'sponsor_id': newcomer.id, 'newcomer_id': admin.id})

        # Now admin tries to vouch newcomer — should hit the circular check.
        self.authenticate('admin', 'admin')
        _csrf = Request.csrf_token(self)
        self.url_open('/my/vouching/give', data={
            'csrf_token': _csrf,
            'newcomer_id': str(newcomer.id),
            'statement': 'Should be blocked',
        })

        reverse = Vouching.search([
            ('sponsor_id', '=', admin.id),
            ('newcomer_id', '=', newcomer.id),
        ])
        self.assertFalse(reverse,
                         f'Circular vouching leaked into DB: {reverse}')


@tagged('social_reputation', 'reputation', 'post_install', '-at_install')
class TestVouchingComputeSudo(TransactionCase):
    """Counts on a profile must reflect reality regardless of the viewer.

    The ir.rule on social_reputation.vouching restricts plain social_users
    to rows where they are sponsor_id or newcomer_id. Without compute_sudo
    on _compute_vouching_counts, a viewer who isn't either always sees
    0 / is_vouched=False on someone else's profile — useless for display."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        group_social = cls.env.ref('social_base.group_social_user')
        cls.sponsor = cls.env['res.users'].create({
            'name': 'Compute Sponsor', 'login': 'compute_sponsor',
            'email': 'cs@rep.test', 'password': 'Test1234!',
            'group_ids': [(4, group_social.id)],
        })
        cls.newcomer = cls.env['res.users'].create({
            'name': 'Compute Newcomer', 'login': 'compute_newcomer',
            'email': 'cn@rep.test', 'password': 'Test1234!',
            'group_ids': [(4, group_social.id)],
        })
        cls.viewer = cls.env['res.users'].create({
            'name': 'Compute Viewer', 'login': 'compute_viewer',
            'email': 'cv@rep.test', 'password': 'Test1234!',
            'group_ids': [(4, group_social.id)],
        })
        cls.env['club_social_profile.profile'].sudo().get_or_create_for_user(cls.newcomer)
        cls.env['social_reputation.vouching'].sudo().create({
            'sponsor_id': cls.sponsor.id,
            'newcomer_id': cls.newcomer.id,
        })

    def test_unrelated_viewer_sees_correct_count(self):
        profile = self.env['club_social_profile.profile'].sudo().search(
            [('user_id', '=', self.newcomer.id)], limit=1)
        as_viewer = profile.with_user(self.viewer)
        self.assertEqual(as_viewer.vouching_received_count, 1)
        self.assertTrue(as_viewer.is_vouched)
        self.assertIn(self.sponsor, as_viewer.sponsor_ids)
