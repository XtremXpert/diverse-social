from datetime import timedelta

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError


class SocialGroupInvitation(models.Model):
    """Admin pushes an invitation to a user — mirror of join_request.

    Join requests flow from the would-be member to the admin (pull).
    Invitations flow the other way (push) so admins can recruit
    specific people without making them discover the group first.
    """
    _name = 'social_group.invitation'
    _description = 'Group Invitation'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc'

    group_id = fields.Many2one(
        'social_group.group', 'Group', required=True, ondelete='cascade', index=True,
    )
    invitee_user_id = fields.Many2one(
        'res.users', 'Invitee', required=True, index=True, ondelete='cascade',
    )
    inviter_user_id = fields.Many2one(
        'res.users', 'Inviter', required=True, default=lambda self: self.env.user,
    )
    create_date = fields.Datetime('Invited', readonly=True)
    message = fields.Text('Personal Message')
    state = fields.Selection([
        ('pending', 'Pending'),
        ('accepted', 'Accepted'),
        ('declined', 'Declined'),
        ('revoked', 'Revoked'),
        ('expired', 'Expired'),
    ], default='pending', required=True, index=True, tracking=True)
    responded_at = fields.Datetime('Responded')
    expires_at = fields.Datetime(
        'Expires',
        default=lambda self: fields.Datetime.now() + timedelta(days=30),
    )

    _unique_pending = models.Constraint(
        "UNIQUE (group_id, invitee_user_id, state) DEFERRABLE INITIALLY DEFERRED",
        "There is already an invitation to this group for that user.",
    )

    @api.constrains('group_id', 'invitee_user_id')
    def _check_not_member(self):
        for rec in self:
            if rec.invitee_user_id in rec.group_id.member_ids:
                raise ValidationError(_(
                    "%(name)s is already a member of this group.",
                    name=rec.invitee_user_id.name,
                ))

    @api.constrains('inviter_user_id', 'invitee_user_id')
    def _check_not_self_invite(self):
        for rec in self:
            if rec.inviter_user_id == rec.invitee_user_id:
                raise ValidationError(_("You cannot invite yourself."))

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for rec in records:
            rec._notify_invitee()
        return records

    def _notify_invitee(self):
        """Drop an in-app notification for the invitee, if the
        club_social_profile.notification helper is installed AND knows
        the 'group_invitation' type (added by social_notifications).
        Silent no-op otherwise — the invitation still exists in DB and
        will surface on /my/groups whenever the invitee visits."""
        self.ensure_one()
        if 'club_social_profile.notification' not in self.env:
            return
        Notification = self.env['club_social_profile.notification']
        valid_types = {code for code, _label in Notification._fields['type'].selection}
        if 'group_invitation' not in valid_types:
            return
        Notification.sudo()._notify(
            user_id=self.invitee_user_id.id,
            actor_id=self.inviter_user_id.id,
            notif_type='group_invitation',
            body=_(
                '%(actor)s invited you to the group "%(group)s".',
                actor=self.inviter_user_id.name,
                group=self.group_id.name,
            ),
            url='/my/groups',
        )

    # ── Actions ──────────────────────────────────────────────────────────

    def action_accept(self):
        self.ensure_one()
        if self.state != 'pending':
            raise UserError(_(
                "This invitation is %s and can no longer be accepted.",
                self._get_state_label(),
            ))
        if self.invitee_user_id != self.env.user:
            raise UserError(_("Only the invited user can accept this invitation."))
        self.group_id.sudo().write({'member_ids': [(4, self.invitee_user_id.id)]})
        self.sudo().write({
            'state': 'accepted',
            'responded_at': fields.Datetime.now(),
        })

    def action_decline(self):
        self.ensure_one()
        if self.state != 'pending':
            raise UserError(_(
                "This invitation is %s and can no longer be declined.",
                self._get_state_label(),
            ))
        if self.invitee_user_id != self.env.user:
            raise UserError(_("Only the invited user can decline this invitation."))
        self.sudo().write({
            'state': 'declined',
            'responded_at': fields.Datetime.now(),
        })

    def action_revoke(self):
        """Inviter (group admin) cancels a pending invitation."""
        self.ensure_one()
        if self.state != 'pending':
            raise UserError(_("Only pending invitations can be revoked."))
        if not self.group_id.is_admin(self.env.user) and self.inviter_user_id != self.env.user:
            raise UserError(_("Only the inviter or a group admin can revoke this."))
        self.sudo().write({
            'state': 'revoked',
            'responded_at': fields.Datetime.now(),
        })

    def _get_state_label(self):
        return dict(self._fields['state'].selection).get(self.state, self.state)

    # ── Cron: expire stale invitations ──────────────────────────────────

    @api.model
    def cron_expire_invitations(self):
        now = fields.Datetime.now()
        stale = self.search([
            ('state', '=', 'pending'),
            ('expires_at', '<', now),
        ])
        if stale:
            stale.write({'state': 'expired', 'responded_at': now})
        return len(stale)
