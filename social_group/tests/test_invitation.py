from odoo.tests import TransactionCase, tagged
from odoo.exceptions import UserError, ValidationError


@tagged('social_group', 'group_invitation', 'post_install', '-at_install')
class TestGroupInvitation(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.group_user = cls.env.ref('base.group_user')
        cls.group_social = cls.env.ref('social_base.group_social_user')

        def _mk_user(login, name):
            return cls.env['res.users'].create({
                'login': login, 'name': name, 'email': f'{login}@inv.test',
                'password': 'Test1234!',
                'group_ids': [(4, cls.group_user.id), (4, cls.group_social.id)],
            })

        cls.admin_user = _mk_user('inv_admin', 'Admin User')
        cls.invitee = _mk_user('inv_invitee', 'Invitee User')
        cls.bystander = _mk_user('inv_bystander', 'Bystander')

        cls.group = cls.env['social_group.group'].sudo().create({
            'name': 'Test Invite Group',
            'privacy': 'private',
            'join_type': 'invite',
            'creator_id': cls.admin_user.id,
            'admin_ids': [(4, cls.admin_user.id)],
            'member_ids': [(4, cls.admin_user.id)],
        })

        cls.Invitation = cls.env['social_group.invitation']

    def _invite(self, invitee, inviter=None, message=None):
        return self.Invitation.sudo().create({
            'group_id': self.group.id,
            'invitee_user_id': invitee.id,
            'inviter_user_id': (inviter or self.admin_user).id,
            'message': message,
        })

    def test_create_invitation_sets_pending(self):
        inv = self._invite(self.invitee)
        self.assertEqual(inv.state, 'pending')
        self.assertEqual(inv.inviter_user_id, self.admin_user)
        self.assertEqual(inv.invitee_user_id, self.invitee)

    def test_cannot_invite_self(self):
        with self.assertRaises(ValidationError):
            self._invite(self.admin_user)

    def test_cannot_invite_existing_member(self):
        self.group.sudo().write({'member_ids': [(4, self.invitee.id)]})
        with self.assertRaises(ValidationError):
            self._invite(self.invitee)

    def test_accept_makes_user_member(self):
        inv = self._invite(self.invitee)
        inv.with_user(self.invitee).action_accept()
        self.assertEqual(inv.state, 'accepted')
        self.assertIn(self.invitee, self.group.sudo().member_ids)

    def test_only_invitee_can_accept(self):
        inv = self._invite(self.invitee)
        with self.assertRaises(UserError):
            inv.with_user(self.bystander).action_accept()
        with self.assertRaises(UserError):
            inv.with_user(self.admin_user).action_accept()

    def test_accept_twice_raises(self):
        inv = self._invite(self.invitee)
        inv.with_user(self.invitee).action_accept()
        with self.assertRaises(UserError):
            inv.with_user(self.invitee).action_accept()

    def test_decline_does_not_add_to_members(self):
        inv = self._invite(self.invitee)
        inv.with_user(self.invitee).action_decline()
        self.assertEqual(inv.state, 'declined')
        self.assertNotIn(self.invitee, self.group.sudo().member_ids)

    def test_only_invitee_can_decline(self):
        inv = self._invite(self.invitee)
        with self.assertRaises(UserError):
            inv.with_user(self.bystander).action_decline()

    def test_admin_can_revoke_pending(self):
        inv = self._invite(self.invitee)
        inv.with_user(self.admin_user).action_revoke()
        self.assertEqual(inv.state, 'revoked')
        self.assertNotIn(self.invitee, self.group.sudo().member_ids)

    def test_revoke_after_accept_raises(self):
        inv = self._invite(self.invitee)
        inv.with_user(self.invitee).action_accept()
        with self.assertRaises(UserError):
            inv.with_user(self.admin_user).action_revoke()

    def test_cron_expires_overdue(self):
        from datetime import timedelta
        from odoo import fields
        inv = self._invite(self.invitee)
        inv.expires_at = fields.Datetime.now() - timedelta(days=1)
        self.Invitation.cron_expire_invitations()
        inv.invalidate_recordset()
        self.assertEqual(inv.state, 'expired')

    def test_cron_ignores_future_expiry(self):
        from datetime import timedelta
        from odoo import fields
        inv = self._invite(self.invitee)
        inv.expires_at = fields.Datetime.now() + timedelta(days=10)
        self.Invitation.cron_expire_invitations()
        inv.invalidate_recordset()
        self.assertEqual(inv.state, 'pending')
