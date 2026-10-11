from odoo.tests import TransactionCase, tagged
from odoo.exceptions import ValidationError, UserError


@tagged('social_consent', 'consent')
class TestConsentGate(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        group_user = cls.env.ref('base.group_user')
        group_social = cls.env.ref('social_base.group_social_user')
        cls.owner_user = cls.env['res.users'].create({
            'name': 'Gate Owner', 'login': 'consent_owner', 'email': 'owner@test.test',
            'group_ids': [(4, group_user.id), (4, group_social.id)],
        })
        cls.visitor_user = cls.env['res.users'].create({
            'name': 'Gate Visitor', 'login': 'consent_visitor', 'email': 'visitor@test.test',
            'group_ids': [(4, group_user.id), (4, group_social.id)],
        })
        cls.Profile = cls.env['club_social_profile.profile']
        cls.owner_profile = cls.Profile.get_or_create_for_user(cls.owner_user)

    def _make_gate(self, min_delay_hours=0):
        gate = self.env['social_consent.gate'].create({
            'profile_id': self.owner_profile.id,
            'is_active': True,
            'min_delay_hours': min_delay_hours,
            'intro_text': 'Please answer before contacting me.',
        })
        check_item = self.env['social_consent.gate_item'].create({
            'gate_id': gate.id,
            'item_type': 'check',
            'text': 'I have read the rules',
            'required': True,
        })
        question_item = self.env['social_consent.gate_item'].create({
            'gate_id': gate.id,
            'item_type': 'question',
            'text': 'How did you hear about me?',
            'required': True,
        })
        return gate, check_item, question_item

    def _make_request_with_answers(self, gate, check_item, question_item, checked=True, text='Friend'):
        req = self.env['social_consent.request'].with_user(self.visitor_user).create({
            'gate_id': gate.id,
            'requester_id': self.visitor_user.id,
        })
        self.env['social_consent.answer'].with_user(self.visitor_user).create({
            'request_id': req.id,
            'item_id': check_item.id,
            'checked': checked,
        })
        self.env['social_consent.answer'].with_user(self.visitor_user).create({
            'request_id': req.id,
            'item_id': question_item.id,
            'text': text,
        })
        return req

    def test_gate_created_for_profile(self):
        gate, _, _ = self._make_gate()
        self.assertEqual(gate.profile_id, self.owner_profile)
        self.assertTrue(gate.is_active)

    def test_duplicate_gate_blocked(self):
        self._make_gate()
        with self.assertRaises(ValidationError):
            self.env['social_consent.gate'].create({
                'profile_id': self.owner_profile.id,
            })

    def test_profile_consent_required(self):
        gate, _, _ = self._make_gate()
        self.owner_profile.invalidate_recordset()
        self.assertTrue(self.owner_profile.consent_required)
        self.assertEqual(self.owner_profile.consent_gate_id, gate)

    def test_submit_request(self):
        gate, check_item, question_item = self._make_gate(min_delay_hours=0)
        req = self._make_request_with_answers(gate, check_item, question_item)
        req.action_submit()
        self.assertEqual(req.state, 'submitted')
        self.assertTrue(req.submitted_at)

    def test_submit_missing_required_check_raises(self):
        gate, check_item, question_item = self._make_gate()
        req = self._make_request_with_answers(gate, check_item, question_item, checked=False)
        with self.assertRaises(ValidationError):
            req.action_submit()

    def test_submit_missing_required_text_raises(self):
        gate, check_item, question_item = self._make_gate()
        req = self._make_request_with_answers(gate, check_item, question_item, text='')
        with self.assertRaises(ValidationError):
            req.action_submit()

    def test_approve_after_no_delay(self):
        gate, check_item, question_item = self._make_gate(min_delay_hours=0)
        req = self._make_request_with_answers(gate, check_item, question_item)
        req.action_submit()
        req.with_user(self.owner_user).action_approve(note='Welcome!')
        self.assertEqual(req.state, 'approved')
        self.assertEqual(req.reviewer_note, 'Welcome!')

    def test_approve_before_delay_raises(self):
        gate, check_item, question_item = self._make_gate(min_delay_hours=72)
        req = self._make_request_with_answers(gate, check_item, question_item)
        req.action_submit()
        with self.assertRaises(UserError):
            req.with_user(self.owner_user).action_approve()

    def test_reject_request(self):
        gate, check_item, question_item = self._make_gate(min_delay_hours=0)
        req = self._make_request_with_answers(gate, check_item, question_item)
        req.action_submit()
        req.with_user(self.owner_user).action_reject(note='Not a match')
        self.assertEqual(req.state, 'rejected')

    def test_withdraw_request(self):
        gate, check_item, question_item = self._make_gate()
        req = self._make_request_with_answers(gate, check_item, question_item)
        req.with_user(self.visitor_user).action_withdraw()
        self.assertEqual(req.state, 'withdrawn')

    def test_duplicate_active_request_blocked(self):
        gate, check_item, question_item = self._make_gate(min_delay_hours=0)
        req = self._make_request_with_answers(gate, check_item, question_item)
        req.action_submit()
        with self.assertRaises(ValidationError):
            self._make_request_with_answers(gate, check_item, question_item)

    def test_non_owner_cannot_approve(self):
        gate, check_item, question_item = self._make_gate(min_delay_hours=0)
        req = self._make_request_with_answers(gate, check_item, question_item)
        req.action_submit()
        stranger = self.env['res.users'].create({
            'name': 'Stranger', 'login': 'consent_stranger', 'email': 'stranger@test.test',
            'group_ids': [
                (4, self.env.ref('base.group_user').id),
                (4, self.env.ref('social_base.group_social_user').id),
            ],
        })
        with self.assertRaises(UserError):
            req.with_user(stranger).action_approve()

    def test_get_consent_status(self):
        gate, check_item, question_item = self._make_gate(min_delay_hours=0)
        self.owner_profile.invalidate_recordset()
        self.assertEqual(
            self.owner_profile.get_consent_status_for(self.visitor_user),
            'none',
        )
        req = self._make_request_with_answers(gate, check_item, question_item)
        req.action_submit()
        self.owner_profile.invalidate_recordset()
        self.assertEqual(
            self.owner_profile.get_consent_status_for(self.visitor_user),
            'submitted',
        )

    def test_pending_count(self):
        gate, check_item, question_item = self._make_gate(min_delay_hours=0)
        req = self._make_request_with_answers(gate, check_item, question_item)
        req.action_submit()
        gate.invalidate_recordset()
        self.assertEqual(gate.pending_count, 1)

    def test_pending_count_decrements_on_approval(self):
        gate, check_item, question_item = self._make_gate(min_delay_hours=0)
        req = self._make_request_with_answers(gate, check_item, question_item)
        req.action_submit()
        req.with_user(self.owner_user).action_approve()
        gate.invalidate_recordset()
        self.assertEqual(gate.pending_count, 0)

    def test_action_mark_under_review(self):
        gate, check_item, question_item = self._make_gate(min_delay_hours=0)
        req = self._make_request_with_answers(gate, check_item, question_item)
        req.action_submit()
        req.with_user(self.owner_user).action_mark_under_review()
        self.assertEqual(req.state, 'under_review')

    def test_action_mark_under_review_wrong_state_raises(self):
        gate, check_item, question_item = self._make_gate(min_delay_hours=0)
        req = self._make_request_with_answers(gate, check_item, question_item)
        # draft → pas encore soumis
        with self.assertRaises(UserError):
            req.with_user(self.owner_user).action_mark_under_review()

    def test_approve_from_under_review(self):
        gate, check_item, question_item = self._make_gate(min_delay_hours=0)
        req = self._make_request_with_answers(gate, check_item, question_item)
        req.action_submit()
        req.with_user(self.owner_user).action_mark_under_review()
        req.with_user(self.owner_user).action_approve()
        self.assertEqual(req.state, 'approved')

    def test_withdraw_approved_raises(self):
        gate, check_item, question_item = self._make_gate(min_delay_hours=0)
        req = self._make_request_with_answers(gate, check_item, question_item)
        req.action_submit()
        req.with_user(self.owner_user).action_approve()
        with self.assertRaises(UserError):
            req.with_user(self.visitor_user).action_withdraw()

    def test_submit_as_non_requester_raises(self):
        gate, check_item, question_item = self._make_gate(min_delay_hours=0)
        req = self._make_request_with_answers(gate, check_item, question_item)
        stranger = self.env['res.users'].create({
            'name': 'Submit Stranger', 'login': 'consent_sub_stranger',
            'email': 'sub_str@test.test',
            'group_ids': [
                (4, self.env.ref('base.group_user').id),
                (4, self.env.ref('social_base.group_social_user').id),
            ],
        })
        with self.assertRaises(UserError):
            req.with_user(stranger).action_submit()

    def test_can_review_false_before_delay(self):
        gate, check_item, question_item = self._make_gate(min_delay_hours=72)
        req = self._make_request_with_answers(gate, check_item, question_item)
        req.action_submit()
        self.assertFalse(req.can_review)

    def test_can_review_false_in_draft(self):
        gate, check_item, question_item = self._make_gate(min_delay_hours=0)
        req = self._make_request_with_answers(gate, check_item, question_item)
        self.assertFalse(req.can_review)

    def test_can_review_true_with_zero_delay(self):
        gate, check_item, question_item = self._make_gate(min_delay_hours=0)
        req = self._make_request_with_answers(gate, check_item, question_item)
        req.action_submit()
        self.assertTrue(req.can_review)

    def test_moderator_can_approve(self):
        gate, check_item, question_item = self._make_gate(min_delay_hours=0)
        req = self._make_request_with_answers(gate, check_item, question_item)
        req.action_submit()
        moderator = self.env['res.users'].create({
            'name': 'Consent Mod', 'login': 'consent_mod',
            'email': 'cmod@test.test',
            'group_ids': [
                (4, self.env.ref('base.group_user').id),
                (4, self.env.ref('social_base.group_social_user').id),
                (4, self.env.ref('social_base.group_social_moderator').id),
            ],
        })
        req.with_user(moderator).action_approve()
        self.assertEqual(req.state, 'approved')

    def test_get_consent_status_approved(self):
        gate, check_item, question_item = self._make_gate(min_delay_hours=0)
        req = self._make_request_with_answers(gate, check_item, question_item)
        req.action_submit()
        req.with_user(self.owner_user).action_approve()
        self.owner_profile.invalidate_recordset()
        self.assertEqual(
            self.owner_profile.get_consent_status_for(self.visitor_user),
            'approved',
        )

    def test_answer_duplicate_raises(self):
        gate, check_item, _ = self._make_gate()
        req = self.env['social_consent.request'].with_user(self.visitor_user).create({
            'gate_id': gate.id, 'requester_id': self.visitor_user.id,
        })
        self.env['social_consent.answer'].create({
            'request_id': req.id, 'item_id': check_item.id, 'checked': True,
        })
        with self.assertRaises(Exception):
            self.env['social_consent.answer'].create({
                'request_id': req.id, 'item_id': check_item.id, 'checked': False,
            })

    def test_reject_sets_reviewed_at(self):
        gate, check_item, question_item = self._make_gate(min_delay_hours=0)
        req = self._make_request_with_answers(gate, check_item, question_item)
        req.action_submit()
        req.with_user(self.owner_user).action_reject(note='Non')
        self.assertTrue(req.reviewed_at)
