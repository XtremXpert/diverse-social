from odoo.tests import HttpCase, TransactionCase, tagged
from odoo.exceptions import UserError


def _make_social_user(env, name, login):
    group_user = env.ref('base.group_user')
    group_social = env.ref('social_base.group_social_user')
    return env['res.users'].create({
        'name': name, 'login': login, 'email': f'{login}@neg.test',
        'password': 'Test1234!',
        'group_ids': [(4, group_user.id), (4, group_social.id)],
    })


def _connect(env, user_a, user_b):
    env['club_social_profile.connection'].sudo().create([
        {'user_id': user_a.id, 'connected_user_id': user_b.id, 'state': 'accepted'},
        {'user_id': user_b.id, 'connected_user_id': user_a.id, 'state': 'accepted'},
    ])


@tagged('social_negotiation', 'portal_negotiation')
class TestPortalNegotiationData(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.initiator = _make_social_user(cls.env, 'NegInitiator', 'neg_initiator')
        cls.partner = _make_social_user(cls.env, 'NegPartner', 'neg_partner')
        cls.other = _make_social_user(cls.env, 'NegOther', 'neg_other')
        _connect(cls.env, cls.initiator, cls.partner)
        cls.Neg = cls.env['social_negotiation.negotiation']
        cls.Item = cls.env['social_negotiation.item']

    def _neg(self, safe_word=False):
        return self.Neg.sudo().create({
            'initiator_id': self.initiator.id,
            'partner_id': self.partner.id,
            'safe_word': safe_word or False,
        })

    def _item(self, neg, text='Activité test', category='desire'):
        return self.Item.sudo().create({
            'negotiation_id': neg.id,
            'text': text,
            'category': category,
        })

    # ── Workflow ──────────────────────────────────────────────────────────

    def test_create_negotiation(self):
        neg = self._neg()
        self.assertEqual(neg.state, 'draft')
        self.assertEqual(neg.initiator_id, self.initiator)

    def test_share(self):
        neg = self._neg()
        neg.with_user(self.initiator).action_share()
        self.assertEqual(neg.state, 'shared')

    def test_cannot_share_twice(self):
        neg = self._neg()
        neg.with_user(self.initiator).action_share()
        with self.assertRaises(UserError):
            neg.with_user(self.initiator).action_share()

    def test_partner_starts_review(self):
        neg = self._neg()
        neg.with_user(self.initiator).action_share()
        neg.with_user(self.partner).action_start_review()
        self.assertEqual(neg.state, 'reviewing')

    def test_both_sign_transitions_active(self):
        neg = self._neg()
        neg.with_user(self.initiator).action_share()
        neg.with_user(self.initiator).action_sign()
        neg.with_user(self.partner).action_sign()
        self.assertEqual(neg.state, 'active')
        self.assertTrue(neg.is_fully_signed)

    def test_archive(self):
        neg = self._neg()
        neg.with_user(self.initiator).action_share()
        neg.with_user(self.initiator).action_archive()
        self.assertEqual(neg.state, 'archived')

    def test_outsider_cannot_act(self):
        neg = self._neg()
        neg.with_user(self.initiator).action_share()
        with self.assertRaises(UserError):
            neg.with_user(self.other).action_sign()

    # ── Items ─────────────────────────────────────────────────────────────

    def test_add_item(self):
        neg = self._neg()
        item = self._item(neg, 'Bondage', 'desire')
        self.assertIn(item, neg.item_ids)

    def test_item_count(self):
        neg = self._neg()
        self._item(neg, 'A')
        self._item(neg, 'B')
        self.assertEqual(neg.item_count, 2)

    def test_delete_item(self):
        neg = self._neg()
        item = self._item(neg)
        item.unlink()
        self.assertFalse(neg.item_ids)

    # ── Réponses et score ─────────────────────────────────────────────────

    def test_agreement_score_all_yes(self):
        neg = self._neg()
        item = self._item(neg)
        item.sudo().write({'initiator_response': 'oui', 'partner_response': 'oui'})
        self.assertEqual(neg.agreement_score, 100)

    def test_agreement_score_conflict(self):
        neg = self._neg()
        item = self._item(neg)
        item.sudo().write({'initiator_response': 'oui', 'partner_response': 'non'})
        self.assertEqual(neg.agreement_score, 0)

    def test_agreement_score_soft_counts(self):
        neg = self._neg()
        item = self._item(neg)
        item.sudo().write({'initiator_response': 'soft', 'partner_response': 'soft'})
        self.assertEqual(neg.agreement_score, 100)

    def test_is_compatible(self):
        neg = self._neg()
        item = self._item(neg)
        item.sudo().write({'initiator_response': 'oui', 'partner_response': 'soft'})
        self.assertTrue(item.is_compatible)

    def test_is_not_compatible_hard_limit(self):
        neg = self._neg()
        item = self._item(neg)
        item.sudo().write({'initiator_response': 'oui', 'partner_response': 'non'})
        self.assertFalse(item.is_compatible)

    # ── Nouvelle version ──────────────────────────────────────────────────

    def test_new_version_increments(self):
        neg = self._neg()
        self._item(neg, 'Item original')
        neg.with_user(self.initiator).action_share()
        neg.with_user(self.initiator).action_sign()
        neg.with_user(self.partner).action_sign()
        new_neg = self.Neg.sudo().browse(neg.id).copy({
            'state': 'draft',
            'version': neg.version + 1,
            'initiator_signed_at': False,
            'partner_signed_at': False,
            'archived_at': False,
        })
        self.assertEqual(new_neg.version, 2)

    # ── Connexions requises ───────────────────────────────────────────────

    def test_not_self_validation(self):
        from odoo.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            self.Neg.sudo().create({
                'initiator_id': self.initiator.id,
                'partner_id': self.initiator.id,
            })


@tagged('social_negotiation', 'portal_negotiation', 'post_install', '-at_install')
class TestPortalNegotiationHttp(HttpCase):

    def _setup_users(self):
        group_user = self.env.ref('base.group_user')
        group_social = self.env.ref('social_base.group_social_user')
        partner = self.env['res.users'].create({
            'name': 'NegHTTPPartner', 'login': 'neg_http_partner',
            'email': 'neg_http_partner@neg.test', 'password': 'Test1234!',
            'group_ids': [(4, group_user.id), (4, group_social.id)],
        })
        admin = self.env.ref('base.user_admin')
        self.env['club_social_profile.connection'].sudo().create([
            {'user_id': admin.id, 'connected_user_id': partner.id, 'state': 'accepted'},
            {'user_id': partner.id, 'connected_user_id': admin.id, 'state': 'accepted'},
        ])
        return partner

    def test_list_unauthenticated_redirects(self):
        resp = self.url_open('/my/negotiation', allow_redirects=False)
        self.assertIn(resp.status_code, (302, 303))

    def test_list_authenticated_ok(self):
        self.authenticate('admin', 'admin')
        _csrf = self.csrf_token()
        resp = self.url_open('/my/negotiation')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'gociation', resp.content)

    def test_list_has_create_form_for_connections(self):
        self._setup_users()
        self.authenticate('admin', 'admin')
        _csrf = self.csrf_token()
        resp = self.url_open('/my/negotiation')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'negotiation/create', resp.content)

    def test_create_negotiation(self):
        partner = self._setup_users()
        self.authenticate('admin', 'admin')
        _csrf = self.csrf_token()
        resp = self.url_open(
            '/my/negotiation/create',
            data={'csrf_token': _csrf, 'partner_id': str(partner.id)},
        )
        self.assertEqual(resp.status_code, 200)
        admin = self.env.ref('base.user_admin')
        neg = self.env['social_negotiation.negotiation'].sudo().search([
            ('initiator_id', '=', admin.id),
            ('partner_id', '=', partner.id),
        ], limit=1)
        self.assertTrue(neg)

    def test_create_non_connection_rejected(self):
        stranger = self.env['res.users'].sudo().create({
            'name': 'Stranger', 'login': 'neg_stranger',
            'email': 'neg_stranger@neg.test', 'password': 'Test1234!',
        })
        self.authenticate('admin', 'admin')
        _csrf = self.csrf_token()
        resp = self.url_open(
            '/my/negotiation/create',
            data={'csrf_token': _csrf, 'partner_id': str(stranger.id)},
        )
        self.assertEqual(resp.status_code, 200)
        admin = self.env.ref('base.user_admin')
        neg = self.env['social_negotiation.negotiation'].sudo().search([
            ('initiator_id', '=', admin.id),
            ('partner_id', '=', stranger.id),
        ], limit=1)
        self.assertFalse(neg)

    def test_detail_page_ok(self):
        partner = self._setup_users()
        admin = self.env.ref('base.user_admin')
        neg = self.env['social_negotiation.negotiation'].sudo().create({
            'initiator_id': admin.id, 'partner_id': partner.id,
        })
        self.authenticate('admin', 'admin')
        _csrf = self.csrf_token()
        resp = self.url_open(f'/my/negotiation/{neg.id}')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'NegHTTPPartner', resp.content)

    def test_detail_outsider_gets_404(self):
        self.authenticate('admin', 'admin')
        _csrf = self.csrf_token()
        resp = self.url_open('/my/negotiation/999999999')
        self.assertEqual(resp.status_code, 404)

    def test_add_item(self):
        partner = self._setup_users()
        admin = self.env.ref('base.user_admin')
        neg = self.env['social_negotiation.negotiation'].sudo().create({
            'initiator_id': admin.id, 'partner_id': partner.id,
        })
        self.authenticate('admin', 'admin')
        _csrf = self.csrf_token()
        resp = self.url_open(
            f'/my/negotiation/{neg.id}/item/add',
            data={'csrf_token': _csrf, 
                'text': 'Bondage léger',
                'category': 'desire',
            },
        )
        self.assertEqual(resp.status_code, 200)
        item = self.env['social_negotiation.item'].sudo().search([
            ('negotiation_id', '=', neg.id), ('text', '=', 'Bondage léger'),
        ], limit=1)
        self.assertTrue(item)

    def test_share_neg(self):
        partner = self._setup_users()
        admin = self.env.ref('base.user_admin')
        neg = self.env['social_negotiation.negotiation'].sudo().create({
            'initiator_id': admin.id, 'partner_id': partner.id,
        })
        self.authenticate('admin', 'admin')
        _csrf = self.csrf_token()
        resp = self.url_open(
            f'/my/negotiation/{neg.id}/share',
            data={'csrf_token': _csrf, },
        )
        self.assertEqual(resp.status_code, 200)
        neg.invalidate_recordset()
        self.assertEqual(neg.state, 'shared')

    def test_respond_to_items(self):
        partner = self._setup_users()
        admin = self.env.ref('base.user_admin')
        neg = self.env['social_negotiation.negotiation'].sudo().create({
            'initiator_id': admin.id, 'partner_id': partner.id, 'state': 'shared',
        })
        item = self.env['social_negotiation.item'].sudo().create({
            'negotiation_id': neg.id, 'text': 'Corde', 'category': 'desire',
        })
        self.authenticate('admin', 'admin')
        _csrf = self.csrf_token()
        resp = self.url_open(
            f'/my/negotiation/{neg.id}/respond',
            data={'csrf_token': _csrf, f'response_{item.id}': 'oui'},
        )
        self.assertEqual(resp.status_code, 200)
        item.invalidate_recordset()
        self.assertEqual(item.initiator_response, 'oui')

    def test_sign(self):
        partner = self._setup_users()
        admin = self.env.ref('base.user_admin')
        neg = self.env['social_negotiation.negotiation'].sudo().create({
            'initiator_id': admin.id, 'partner_id': partner.id, 'state': 'reviewing',
        })
        self.authenticate('admin', 'admin')
        _csrf = self.csrf_token()
        resp = self.url_open(
            f'/my/negotiation/{neg.id}/sign',
            data={'csrf_token': _csrf, },
        )
        self.assertEqual(resp.status_code, 200)
        neg.invalidate_recordset()
        self.assertTrue(neg.initiator_signed_at)

    # ── Supprimer un item ─────────────────────────────────────────────────

    def test_item_delete_by_initiator(self):
        partner = self._setup_users()
        admin = self.env.ref('base.user_admin')
        neg = self.env['social_negotiation.negotiation'].sudo().create({
            'initiator_id': admin.id, 'partner_id': partner.id,
        })
        item = self.env['social_negotiation.item'].sudo().create({
            'negotiation_id': neg.id, 'text': 'Item à supprimer', 'category': 'desire',
        })
        self.authenticate('admin', 'admin')
        _csrf = self.csrf_token()
        resp = self.url_open(
            f'/my/negotiation/{neg.id}/item/{item.id}/delete',
            data={'csrf_token': _csrf, },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(self.env['social_negotiation.item'].sudo().browse(item.id).exists())

    def test_item_delete_by_partner_forbidden(self):
        partner = self._setup_users()
        admin = self.env.ref('base.user_admin')
        neg = self.env['social_negotiation.negotiation'].sudo().create({
            'initiator_id': admin.id, 'partner_id': partner.id,
        })
        item = self.env['social_negotiation.item'].sudo().create({
            'negotiation_id': neg.id, 'text': 'Item protégé', 'category': 'desire',
        })
        self.authenticate('neg_http_partner', 'Test1234!')
        _csrf = self.csrf_token()
        resp = self.url_open(
            f'/my/negotiation/{neg.id}/item/{item.id}/delete',
            data={'csrf_token': _csrf, },
        )
        self.assertEqual(resp.status_code, 403)

    def test_item_delete_non_draft_forbidden(self):
        partner = self._setup_users()
        admin = self.env.ref('base.user_admin')
        neg = self.env['social_negotiation.negotiation'].sudo().create({
            'initiator_id': admin.id, 'partner_id': partner.id, 'state': 'shared',
        })
        item = self.env['social_negotiation.item'].sudo().create({
            'negotiation_id': neg.id, 'text': 'Item partagé', 'category': 'desire',
        })
        self.authenticate('admin', 'admin')
        _csrf = self.csrf_token()
        resp = self.url_open(
            f'/my/negotiation/{neg.id}/item/{item.id}/delete',
            data={'csrf_token': _csrf, },
        )
        self.assertEqual(resp.status_code, 403)

    # ── Sécurité partage / ajout item ────────────────────────────────────

    def test_share_by_partner_forbidden(self):
        partner = self._setup_users()
        admin = self.env.ref('base.user_admin')
        neg = self.env['social_negotiation.negotiation'].sudo().create({
            'initiator_id': admin.id, 'partner_id': partner.id,
        })
        self.authenticate('neg_http_partner', 'Test1234!')
        _csrf = self.csrf_token()
        resp = self.url_open(
            f'/my/negotiation/{neg.id}/share',
            data={'csrf_token': _csrf, },
        )
        self.assertEqual(resp.status_code, 403)

    def test_add_item_by_partner_forbidden(self):
        partner = self._setup_users()
        admin = self.env.ref('base.user_admin')
        neg = self.env['social_negotiation.negotiation'].sudo().create({
            'initiator_id': admin.id, 'partner_id': partner.id,
        })
        self.authenticate('neg_http_partner', 'Test1234!')
        _csrf = self.csrf_token()
        resp = self.url_open(
            f'/my/negotiation/{neg.id}/item/add',
            data={'csrf_token': _csrf, 'text': 'Tentative', 'category': 'desire'},
        )
        self.assertEqual(resp.status_code, 403)

    def test_add_item_non_draft_forbidden(self):
        partner = self._setup_users()
        admin = self.env.ref('base.user_admin')
        neg = self.env['social_negotiation.negotiation'].sudo().create({
            'initiator_id': admin.id, 'partner_id': partner.id, 'state': 'shared',
        })
        self.authenticate('admin', 'admin')
        _csrf = self.csrf_token()
        resp = self.url_open(
            f'/my/negotiation/{neg.id}/item/add',
            data={'csrf_token': _csrf, 'text': 'Nouvel item', 'category': 'desire'},
        )
        self.assertEqual(resp.status_code, 403)

    def test_respond_draft_state_forbidden(self):
        partner = self._setup_users()
        admin = self.env.ref('base.user_admin')
        neg = self.env['social_negotiation.negotiation'].sudo().create({
            'initiator_id': admin.id, 'partner_id': partner.id,
        })
        item = self.env['social_negotiation.item'].sudo().create({
            'negotiation_id': neg.id, 'text': 'Item', 'category': 'desire',
        })
        self.authenticate('admin', 'admin')
        _csrf = self.csrf_token()
        resp = self.url_open(
            f'/my/negotiation/{neg.id}/respond',
            data={'csrf_token': _csrf, f'response_{item.id}': 'oui'},
        )
        self.assertEqual(resp.status_code, 403)

    # ── Archiver ──────────────────────────────────────────────────────────

    def test_archive_neg(self):
        partner = self._setup_users()
        admin = self.env.ref('base.user_admin')
        neg = self.env['social_negotiation.negotiation'].sudo().create({
            'initiator_id': admin.id, 'partner_id': partner.id, 'state': 'shared',
        })
        self.authenticate('admin', 'admin')
        _csrf = self.csrf_token()
        resp = self.url_open(
            f'/my/negotiation/{neg.id}/archive',
            data={'csrf_token': _csrf, },
        )
        self.assertEqual(resp.status_code, 200)
        neg.invalidate_recordset()
        self.assertEqual(neg.state, 'archived')

    # ── Nouvelle version ──────────────────────────────────────────────────

    def test_new_version_creates_draft(self):
        partner = self._setup_users()
        admin = self.env.ref('base.user_admin')
        neg = self.env['social_negotiation.negotiation'].sudo().create({
            'initiator_id': admin.id, 'partner_id': partner.id, 'state': 'active',
        })
        self.env['social_negotiation.item'].sudo().create({
            'negotiation_id': neg.id, 'text': 'Item versionné', 'category': 'desire',
        })
        self.authenticate('admin', 'admin')
        _csrf = self.csrf_token()
        resp = self.url_open(
            f'/my/negotiation/{neg.id}/new_version',
            data={'csrf_token': _csrf, },
        )
        self.assertEqual(resp.status_code, 200)
        neg.invalidate_recordset()
        self.assertEqual(neg.state, 'archived')
        new_neg = self.env['social_negotiation.negotiation'].sudo().search([
            ('initiator_id', '=', admin.id),
            ('partner_id', '=', partner.id),
            ('state', '=', 'draft'),
            ('version', '=', 2),
        ], limit=1)
        self.assertTrue(new_neg)
        new_item = self.env['social_negotiation.item'].sudo().search([
            ('negotiation_id', '=', new_neg.id), ('text', '=', 'Item versionné'),
        ], limit=1)
        self.assertTrue(new_item)
