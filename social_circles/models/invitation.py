from datetime import timedelta

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError


class SocialCircleInvitation(models.Model):
    """Invitation à rejoindre un cercle de confiance.

    Décision produit : ranger quelqu'un dans un cercle passe TOUJOURS par son
    accord (même entre connexions), contrairement à `circle.add_member` qui est
    unilatéral. L'ajout effectif se fait à l'acceptation.
    """
    _name = "social_circles.invitation"
    _description = "Circle Invitation"
    _inherit = ["mail.thread"]
    _order = "create_date desc"

    circle_id = fields.Many2one(
        "social_circles.circle", required=True, ondelete="cascade", index=True)
    inviter_user_id = fields.Many2one(
        "res.users", "Inviter", required=True, index=True,
        default=lambda self: self.env.user, ondelete="cascade")
    invitee_user_id = fields.Many2one(
        "res.users", "Invitee", required=True, index=True, ondelete="cascade")
    create_date = fields.Datetime("Invited", readonly=True)
    message = fields.Text("Personal Message")
    state = fields.Selection([
        ("pending", "Pending"),
        ("accepted", "Accepted"),
        ("declined", "Declined"),
        ("revoked", "Revoked"),
        ("expired", "Expired"),
    ], default="pending", required=True, index=True, tracking=True)
    responded_at = fields.Datetime("Responded")
    expires_at = fields.Datetime(
        "Expires",
        default=lambda self: fields.Datetime.now() + timedelta(days=30))

    _unique_pending = models.Constraint(
        "UNIQUE (circle_id, invitee_user_id, state) DEFERRABLE INITIALLY DEFERRED",
        "There is already an invitation to this circle for that user.")

    @api.constrains("circle_id", "invitee_user_id")
    def _check_not_member(self):
        for rec in self:
            if rec.invitee_user_id in rec.circle_id.member_ids:
                raise ValidationError(_("This person is already in the circle."))

    @api.constrains("inviter_user_id", "invitee_user_id")
    def _check_not_self(self):
        for rec in self:
            if rec.inviter_user_id == rec.invitee_user_id:
                raise ValidationError(_("You cannot invite yourself."))

    @api.constrains("circle_id", "inviter_user_id")
    def _check_owner(self):
        """Seul le propriétaire du cercle peut y inviter."""
        for rec in self:
            if rec.circle_id.profile_id.user_id != rec.inviter_user_id:
                raise ValidationError(_(
                    "Only the circle owner can invite people to it."))

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for rec in records:
            rec._notify_invitee()
        return records

    def _notify_invitee(self):
        self.ensure_one()
        if "club_social_profile.notification" not in self.env:
            return
        Notification = self.env["club_social_profile.notification"]
        valid = {code for code, _lbl in Notification._fields["type"].selection}
        # Réutilise le type circle_added (ajouté par social_notifications) ;
        # sinon no-op — l'invitation reste visible sur /my/circles.
        notif_type = "circle_added" if "circle_added" in valid else None
        if not notif_type:
            return
        Profile = self.env["club_social_profile.profile"]
        Notification.sudo()._notify(
            user_id=self.invitee_user_id.id,
            actor_id=self.inviter_user_id.id,
            notif_type=notif_type,
            body=_(
                '%(actor)s invited you to a trust circle.',
                actor=Profile._display_name_for_user(self.inviter_user_id)),
            url="/my/circles",
        )

    # ── Actions ───────────────────────────────────────────────────────────────

    def action_accept(self):
        self.ensure_one()
        if self.state != "pending":
            raise UserError(_("This invitation can no longer be accepted."))
        if self.invitee_user_id != self.env.user:
            raise UserError(_("Only the invited user can accept this invitation."))
        # L'invité n'est pas encore membre → il ne peut pas lire le cercle ;
        # l'ajout se fait donc en sudo.
        self.circle_id.sudo().add_member(self.invitee_user_id)
        self.sudo().write({
            "state": "accepted", "responded_at": fields.Datetime.now()})

    def action_decline(self):
        self.ensure_one()
        if self.state != "pending":
            raise UserError(_("This invitation can no longer be declined."))
        if self.invitee_user_id != self.env.user:
            raise UserError(_("Only the invited user can decline this invitation."))
        self.sudo().write({
            "state": "declined", "responded_at": fields.Datetime.now()})

    def action_revoke(self):
        self.ensure_one()
        if self.state != "pending":
            raise UserError(_("Only pending invitations can be revoked."))
        if self.circle_id.profile_id.user_id != self.env.user:
            raise UserError(_("Only the circle owner can revoke this."))
        self.sudo().write({
            "state": "revoked", "responded_at": fields.Datetime.now()})

    @api.model
    def cron_expire_invitations(self):
        now = fields.Datetime.now()
        stale = self.search([("state", "=", "pending"), ("expires_at", "<", now)])
        if stale:
            stale.write({"state": "expired", "responded_at": now})
        return len(stale)
