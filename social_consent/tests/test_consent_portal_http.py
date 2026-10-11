from odoo.tests import HttpCase, tagged


@tagged('social_consent', 'consent_portal', 'post_install', '-at_install')
class TestConsentPortalHttp(HttpCase):

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _setup_gate(self):
        """Gate pour admin avec 1 check + 1 question, min_delay=0."""
        admin = self.env.ref('base.user_admin')
        profile = (
            self.env['club_social_profile.profile'].sudo().search(
                [('user_id', '=', admin.id)], limit=1
            )
            or self.env['club_social_profile.profile'].sudo().create({'user_id': admin.id})
        )
        # Make sure there is no existing gate (tests can share the DB)
        gate = self.env['social_consent.gate'].sudo().search(
            [('profile_id', '=', profile.id)], limit=1
        )
        if not gate:
            gate = self.env['social_consent.gate'].sudo().create({
                'profile_id': profile.id,
                'is_active': True,
                'min_delay_hours': 0,
                'intro_text': 'Please answer before contacting me.',
            })
        check_item = self.env['social_consent.gate_item'].sudo().create({
            'gate_id': gate.id,
            'item_type': 'check',
            'text': "J'accepte les conditions",
            'required': True,
        })
        question_item = self.env['social_consent.gate_item'].sudo().create({
            'gate_id': gate.id,
            'item_type': 'question',
            'text': 'How did you find me?',
            'required': True,
        })
        return gate, check_item, question_item

    def _setup_visitor(self):
        group_user = self.env.ref('base.group_user')
        group_social = self.env.ref('social_base.group_social_user')
        return self.env['res.users'].sudo().create({
            'name': 'ConsentVisitor',
            'login': 'consent_visitor_http',
            'email': 'visitor@consent.test',
            'password': 'Test1234!',
            'group_ids': [(4, group_user.id), (4, group_social.id)],
        })

    def _submit_request(self, gate, check_item, question_item, visitor):
        """Create and submit a request (visitor as requester)."""
        req = self.env['social_consent.request'].with_user(visitor).create({
            'gate_id': gate.id,
            'requester_id': visitor.id,
        })
        self.env['social_consent.answer'].sudo().create([
            {'request_id': req.id, 'item_id': check_item.id, 'checked': True},
            {'request_id': req.id, 'item_id': question_item.id, 'text': 'Via un ami'},
        ])
        req.with_user(visitor).action_submit()
        return req

    # ── /my/consent ───────────────────────────────────────────────────────────

    def test_my_consent_unauthenticated_redirects(self):
        resp = self.url_open('/my/consent', allow_redirects=False)
        self.assertIn(resp.status_code, (302, 303))

    def test_my_consent_authenticated_ok(self):
        self.authenticate('admin', 'admin')
        _csrf = self.csrf_token()
        resp = self.url_open('/my/consent')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'consent', resp.content.lower())

    # ── /my/consent/gate ──────────────────────────────────────────────────────

    def test_my_gate_page_ok(self):
        self.authenticate('admin', 'admin')
        _csrf = self.csrf_token()
        resp = self.url_open('/my/consent/gate')
        self.assertEqual(resp.status_code, 200)

    def test_save_gate_settings(self):
        self.authenticate('admin', 'admin')
        _csrf = self.csrf_token()
        resp = self.url_open(
            '/my/consent/gate/save',
            data={'csrf_token': _csrf, 
                'intro_text': 'Bienvenue sur ma gate de consentement',
                'min_delay_hours': '48',
                'require_all_checks': 'on',
            },
        )
        self.assertEqual(resp.status_code, 200)
        admin = self.env.ref('base.user_admin')
        profile = self.env['club_social_profile.profile'].sudo().search(
            [('user_id', '=', admin.id)], limit=1
        )
        if profile:
            gate = self.env['social_consent.gate'].sudo().search(
                [('profile_id', '=', profile.id)], limit=1
            )
            if gate:
                self.assertEqual(gate.min_delay_hours, 48)

    def test_toggle_gate_changes_active_state(self):
        gate, _, _ = self._setup_gate()
        initial = gate.is_active
        self.authenticate('admin', 'admin')
        _csrf = self.csrf_token()
        self.url_open('/my/consent/gate/toggle', data={'csrf_token': _csrf, })
        gate.invalidate_recordset()
        self.assertNotEqual(gate.is_active, initial)

    def test_add_gate_item_ok(self):
        self._setup_gate()
        self.authenticate('admin', 'admin')
        _csrf = self.csrf_token()
        resp = self.url_open(
            '/my/consent/gate/item/add',
            data={'csrf_token': _csrf, 
                'item_type': 'check',
                'text': 'Je respecte la charte',
                'required': 'on',
            },
        )
        self.assertEqual(resp.status_code, 200)
        admin = self.env.ref('base.user_admin')
        profile = self.env['club_social_profile.profile'].sudo().search(
            [('user_id', '=', admin.id)], limit=1
        )
        if profile:
            gate = self.env['social_consent.gate'].sudo().search(
                [('profile_id', '=', profile.id)], limit=1
            )
            if gate:
                item = self.env['social_consent.gate_item'].sudo().search([
                    ('gate_id', '=', gate.id), ('text', '=', 'Je respecte la charte'),
                ], limit=1)
                self.assertTrue(item)

    def test_add_gate_item_empty_text_shows_error(self):
        self._setup_gate()
        self.authenticate('admin', 'admin')
        _csrf = self.csrf_token()
        resp = self.url_open(
            '/my/consent/gate/item/add',
            data={'csrf_token': _csrf, 'item_type': 'check', 'text': ''},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'obligatoire', resp.content)

    def test_delete_gate_item_by_owner(self):
        gate, check_item, _ = self._setup_gate()
        self.authenticate('admin', 'admin')
        _csrf = self.csrf_token()
        resp = self.url_open(
            f'/my/consent/gate/item/{check_item.id}/delete',
            data={'csrf_token': _csrf, },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(
            self.env['social_consent.gate_item'].sudo().browse(check_item.id).exists()
        )

    def test_delete_gate_item_by_non_owner_forbidden(self):
        gate, check_item, _ = self._setup_gate()
        self._setup_visitor()
        self.authenticate('consent_visitor_http', 'Test1234!')
        _csrf = self.csrf_token()
        resp = self.url_open(
            f'/my/consent/gate/item/{check_item.id}/delete',
            data={'csrf_token': _csrf, },
        )
        self.assertEqual(resp.status_code, 403)

    # ── /my/consent/received et /sent ─────────────────────────────────────────

    def test_received_requests_ok(self):
        self._setup_gate()
        self.authenticate('admin', 'admin')
        _csrf = self.csrf_token()
        resp = self.url_open('/my/consent/received')
        self.assertEqual(resp.status_code, 200)

    def test_sent_requests_ok(self):
        self.authenticate('admin', 'admin')
        _csrf = self.csrf_token()
        resp = self.url_open('/my/consent/sent')
        self.assertEqual(resp.status_code, 200)

    # ── /consent/gate/<id> ────────────────────────────────────────────────────

    def test_view_gate_form_ok(self):
        gate, _, _ = self._setup_gate()
        self.authenticate('admin', 'admin')
        _csrf = self.csrf_token()
        resp = self.url_open(f'/consent/gate/{gate.id}')
        self.assertEqual(resp.status_code, 200)
        # Structural marker: the consent form posts to the /start endpoint
        # for this gate id.
        self.assertIn(f'/consent/gate/{gate.id}/start'.encode(), resp.content)

    def test_view_inactive_gate_returns_404(self):
        gate, _, _ = self._setup_gate()
        gate.sudo().write({'is_active': False})
        self.authenticate('admin', 'admin')
        _csrf = self.csrf_token()
        resp = self.url_open(f'/consent/gate/{gate.id}')
        self.assertEqual(resp.status_code, 404)

    def test_start_request_ok(self):
        gate, check_item, question_item = self._setup_gate()
        visitor = self._setup_visitor()
        self.authenticate('consent_visitor_http', 'Test1234!')
        _csrf = self.csrf_token()
        resp = self.url_open(
            f'/consent/gate/{gate.id}/start',
            data={'csrf_token': _csrf, 
                f'check_{check_item.id}': 'on',
                f'text_{question_item.id}': 'Via un ami',
            },
        )
        self.assertEqual(resp.status_code, 200)
        req = self.env['social_consent.request'].sudo().search([
            ('gate_id', '=', gate.id), ('requester_id', '=', visitor.id),
        ], limit=1)
        self.assertTrue(req)
        self.assertEqual(req.state, 'submitted')

    def test_start_request_missing_required_check_shows_error(self):
        gate, check_item, question_item = self._setup_gate()
        self._setup_visitor()
        self.authenticate('consent_visitor_http', 'Test1234!')
        _csrf = self.csrf_token()
        resp = self.url_open(
            f'/consent/gate/{gate.id}/start',
            data={'csrf_token': _csrf, 
                # check_{check_item.id} absent → checked=False → ValidationError
                f'text_{question_item.id}': 'Via un ami',
            },
        )
        self.assertEqual(resp.status_code, 200)
        # Pas de redirection vers /consent/request/
        self.assertNotIn(b'/consent/request/', resp.url.encode())

    # ── /consent/request/<id> ─────────────────────────────────────────────────

    def test_view_request_as_requester(self):
        gate, check_item, question_item = self._setup_gate()
        visitor = self._setup_visitor()
        req = self._submit_request(gate, check_item, question_item, visitor)
        self.authenticate('consent_visitor_http', 'Test1234!')
        _csrf = self.csrf_token()
        resp = self.url_open(f'/consent/request/{req.id}')
        self.assertEqual(resp.status_code, 200)

    def test_view_request_as_gate_owner(self):
        gate, check_item, question_item = self._setup_gate()
        visitor = self._setup_visitor()
        req = self._submit_request(gate, check_item, question_item, visitor)
        self.authenticate('admin', 'admin')
        _csrf = self.csrf_token()
        resp = self.url_open(f'/consent/request/{req.id}')
        self.assertEqual(resp.status_code, 200)

    def test_view_request_as_outsider_returns_404(self):
        gate, check_item, question_item = self._setup_gate()
        visitor = self._setup_visitor()
        req = self._submit_request(gate, check_item, question_item, visitor)
        group_user = self.env.ref('base.group_user')
        group_social = self.env.ref('social_base.group_social_user')
        outsider = self.env['res.users'].sudo().create({
            'name': 'Outsider', 'login': 'consent_outsider_http',
            'email': 'outsider@consent.test', 'password': 'Test1234!',
            'group_ids': [(4, group_user.id), (4, group_social.id)],
        })
        self.authenticate('consent_outsider_http', 'Test1234!')
        _csrf = self.csrf_token()
        resp = self.url_open(f'/consent/request/{req.id}')
        self.assertEqual(resp.status_code, 404)

    def test_approve_request_by_gate_owner(self):
        gate, check_item, question_item = self._setup_gate()
        visitor = self._setup_visitor()
        req = self._submit_request(gate, check_item, question_item, visitor)
        self.authenticate('admin', 'admin')
        _csrf = self.csrf_token()
        resp = self.url_open(
            f'/consent/request/{req.id}/approve',
            data={'csrf_token': _csrf, 'note': 'Bienvenue !'},
        )
        self.assertEqual(resp.status_code, 200)
        req.invalidate_recordset()
        self.assertEqual(req.state, 'approved')

    def test_reject_request_by_gate_owner(self):
        gate, check_item, question_item = self._setup_gate()
        visitor = self._setup_visitor()
        req = self._submit_request(gate, check_item, question_item, visitor)
        self.authenticate('admin', 'admin')
        _csrf = self.csrf_token()
        resp = self.url_open(
            f'/consent/request/{req.id}/reject',
            data={'csrf_token': _csrf, 'note': 'Sorry, not a match'},
        )
        self.assertEqual(resp.status_code, 200)
        req.invalidate_recordset()
        self.assertEqual(req.state, 'rejected')

    def test_withdraw_request_by_requester(self):
        gate, check_item, question_item = self._setup_gate()
        visitor = self._setup_visitor()
        req = self._submit_request(gate, check_item, question_item, visitor)
        self.authenticate('consent_visitor_http', 'Test1234!')
        _csrf = self.csrf_token()
        resp = self.url_open(
            f'/consent/request/{req.id}/withdraw',
            data={'csrf_token': _csrf, },
        )
        self.assertEqual(resp.status_code, 200)
        req.invalidate_recordset()
        self.assertEqual(req.state, 'withdrawn')
