from odoo.tests import TransactionCase, tagged
from odoo.exceptions import ValidationError


@tagged('social_group', 'group')
class TestSocialGroup(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        group_user = cls.env.ref('base.group_user')
        group_social = cls.env.ref('social_base.group_social_user')
        cls.user1 = cls.env['res.users'].create({
            'name': 'Group User 1', 'login': 'group_test_user1', 'email': 'group1@test.test',
            'group_ids': [(4, group_user.id), (4, group_social.id)],
        })
        cls.user2 = cls.env['res.users'].create({
            'name': 'Group User 2', 'login': 'group_test_user2', 'email': 'group2@test.test',
            'group_ids': [(4, group_user.id), (4, group_social.id)],
        })
        cls.Group = cls.env['social_group.group']

    def _make_group(self, privacy='public', join_type='open'):
        return self.Group.with_user(self.user1).create({
            'name': 'Test Group',
            'privacy': privacy,
            'join_type': join_type,
            'member_ids': [(4, self.user1.id)],
            'admin_ids': [(4, self.user1.id)],
        })

    def test_create_group(self):
        group = self._make_group()
        self.assertEqual(group.creator_id, self.user1)
        self.assertIn(self.user1, group.member_ids)

    def test_join_open_group(self):
        group = self._make_group(privacy='public', join_type='open')
        group.with_user(self.user2).action_join()
        self.assertIn(self.user2, group.member_ids)

    def test_join_approval_creates_request(self):
        group = self._make_group(privacy='private', join_type='approval')
        group.with_user(self.user2).action_join()
        request = self.env['social_group.join_request'].search([
            ('group_id', '=', group.id), ('user_id', '=', self.user2.id),
        ])
        self.assertEqual(request.state, 'pending')

    def test_approve_join_request(self):
        group = self._make_group(privacy='private', join_type='approval')
        group.with_user(self.user2).action_join()
        req = self.env['social_group.join_request'].search([('group_id', '=', group.id)])
        req.with_user(self.user1).action_approve()
        self.assertIn(self.user2, group.member_ids)
        self.assertEqual(req.state, 'approved')

    def test_invite_only_raises(self):
        group = self._make_group(join_type='invite')
        with self.assertRaises(ValidationError):
            group.with_user(self.user2).action_join()

    def test_sole_admin_cannot_leave(self):
        group = self._make_group()
        with self.assertRaises(ValidationError):
            group.with_user(self.user1).action_leave()

    def test_post_linked_to_group(self):
        group = self._make_group()
        post = self.env['social_base.post'].with_user(self.user1).create({
            'content': 'Group post', 'group_id': group.id,
        })
        self.assertIn(post, group.post_ids)
        self.assertEqual(group.post_count, 1)

    # ── Reject join request ───────────────────────────────────────────────────

    def test_reject_join_request(self):
        group = self._make_group(privacy='private', join_type='approval')
        group.with_user(self.user2).action_join()
        req = self.env['social_group.join_request'].search([('group_id', '=', group.id)])
        req.with_user(self.user1).action_reject()
        self.assertEqual(req.state, 'rejected')
        self.assertNotIn(self.user2, group.member_ids)

    def test_reject_records_processed_by(self):
        group = self._make_group(privacy='private', join_type='approval')
        group.with_user(self.user2).action_join()
        req = self.env['social_group.join_request'].search([('group_id', '=', group.id)])
        req.with_user(self.user1).action_reject()
        self.assertEqual(req.processed_by, self.user1)
        self.assertTrue(req.processed_date)

    def test_approve_records_processed_by(self):
        group = self._make_group(privacy='private', join_type='approval')
        group.with_user(self.user2).action_join()
        req = self.env['social_group.join_request'].search([('group_id', '=', group.id)])
        req.with_user(self.user1).action_approve()
        self.assertEqual(req.processed_by, self.user1)
        self.assertTrue(req.processed_date)

    # ── Leave ─────────────────────────────────────────────────────────────────

    def test_non_admin_can_leave(self):
        group = self._make_group()
        group.sudo().write({'member_ids': [(4, self.user2.id)]})
        group.with_user(self.user2).action_leave()
        self.assertNotIn(self.user2, group.member_ids)

    # ── Computed ──────────────────────────────────────────────────────────────

    def test_member_count(self):
        group = self._make_group()
        group.sudo().write({'member_ids': [(4, self.user2.id)]})
        self.assertEqual(group.member_count, 2)

    # ── is_member / is_admin / is_moderator ───────────────────────────────────

    def test_is_member_true(self):
        group = self._make_group()
        self.assertTrue(group.is_member(self.user1))

    def test_is_member_false(self):
        group = self._make_group()
        self.assertFalse(group.is_member(self.user2))

    def test_is_admin_true(self):
        group = self._make_group()
        self.assertTrue(group.is_admin(self.user1))

    def test_is_admin_false(self):
        group = self._make_group()
        self.assertFalse(group.is_admin(self.user2))

    def test_is_moderator_for_creator(self):
        group = self._make_group()
        self.assertTrue(group.is_moderator(self.user1))

    def test_is_moderator_for_admin(self):
        group = self._make_group()
        group.sudo().write({'admin_ids': [(4, self.user2.id)]})
        self.assertTrue(group.is_moderator(self.user2))

    def test_is_moderator_for_moderated_by(self):
        group = self._make_group()
        group.sudo().write({'moderated_by': [(4, self.user2.id)]})
        self.assertTrue(group.is_moderator(self.user2))

    def test_is_not_moderator(self):
        group = self._make_group()
        self.assertFalse(group.is_moderator(self.user2))

    # ── Rules ─────────────────────────────────────────────────────────────────

    def test_group_rule_created(self):
        group = self._make_group()
        rule = self.env['social_group.rule'].sudo().create({
            'group_id': group.id,
            'name': 'Respectez les autres',
        })
        self.assertIn(rule, group.rule_ids)

    def test_group_rule_ordered_by_sequence(self):
        group = self._make_group()
        r2 = self.env['social_group.rule'].sudo().create({'group_id': group.id, 'name': 'R2', 'sequence': 20})
        r1 = self.env['social_group.rule'].sudo().create({'group_id': group.id, 'name': 'R1', 'sequence': 10})
        rules = self.env['social_group.rule'].search([('group_id', '=', group.id)])
        self.assertEqual(rules[0], r1)
        self.assertEqual(rules[1], r2)

    # ── Cron ──────────────────────────────────────────────────────────────────

    def test_cron_deletes_old_processed_requests(self):
        from odoo import fields
        from datetime import timedelta
        group = self._make_group(privacy='private', join_type='approval')
        group.with_user(self.user2).action_join()
        req = self.env['social_group.join_request'].search([('group_id', '=', group.id)])
        req.with_user(self.user1).action_approve()
        req.sudo().write({'processed_date': fields.Datetime.now() - timedelta(days=31)})
        req_id = req.id
        self.env['social_group.join_request'].cron_cleanup_old_requests()
        self.assertFalse(self.env['social_group.join_request'].sudo().browse(req_id).exists())

    def test_cron_keeps_pending_requests(self):
        group = self._make_group(privacy='private', join_type='approval')
        group.with_user(self.user2).action_join()
        req = self.env['social_group.join_request'].search([('group_id', '=', group.id)])
        self.assertEqual(req.state, 'pending')
        self.env['social_group.join_request'].cron_cleanup_old_requests()
        self.assertTrue(self.env['social_group.join_request'].sudo().browse(req.id).exists())

    def test_cron_keeps_recent_processed_requests(self):
        group = self._make_group(privacy='private', join_type='approval')
        group.with_user(self.user2).action_join()
        req = self.env['social_group.join_request'].search([('group_id', '=', group.id)])
        req.with_user(self.user1).action_approve()
        self.env['social_group.join_request'].cron_cleanup_old_requests()
        self.assertTrue(self.env['social_group.join_request'].sudo().browse(req.id).exists())

    def test_cron_returns_count(self):
        from odoo import fields
        from datetime import timedelta
        group = self._make_group(privacy='private', join_type='approval')
        group.with_user(self.user2).action_join()
        req = self.env['social_group.join_request'].search([('group_id', '=', group.id)])
        req.with_user(self.user1).action_reject()
        req.sudo().write({'processed_date': fields.Datetime.now() - timedelta(days=31)})
        count = self.env['social_group.join_request'].cron_cleanup_old_requests()
        self.assertGreaterEqual(count, 1)
