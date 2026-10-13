from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

_GROUP = "event_portal_create.group_event_portal_organiser"


class OrganiserRequest(models.Model):
    """Demande d'un participant pour devenir organisateur portail.

    Flux : le membre soumet une demande depuis le portail (état pending) ; un
    modérateur l'approuve (accorde le groupe organisateur) ou la refuse.
    """
    _name = "event_portal_create.organiser_request"
    _description = "Demande pour devenir organisateur"
    _inherit = ["mail.thread"]
    _order = "create_date desc"

    user_id = fields.Many2one(
        "res.users", string="Demandeur", required=True, index=True,
        ondelete="cascade", default=lambda self: self.env.user,
        tracking=True)
    partner_id = fields.Many2one(related="user_id.partner_id", store=True)
    motivation = fields.Text("Motivation")
    state = fields.Selection([
        ("pending", "En attente"),
        ("approved", "Approuvée"),
        ("rejected", "Refusée"),
    ], default="pending", required=True, index=True, tracking=True)
    reviewer_id = fields.Many2one("res.users", string="Traitée par", readonly=True)
    reviewed_at = fields.Datetime("Traitée le", readonly=True)
    review_note = fields.Text("Note du modérateur")

    @api.constrains("user_id", "state")
    def _check_single_pending(self):
        for rec in self.filtered(lambda r: r.state == "pending"):
            dup = self.search_count([
                ("user_id", "=", rec.user_id.id),
                ("state", "=", "pending"),
                ("id", "!=", rec.id),
            ])
            if dup:
                raise ValidationError(_(
                    "Une demande est déjà en attente pour cette personne."))

    # ── API portail ───────────────────────────────────────────────────────────

    @api.model
    def _has_pending(self, user):
        return bool(self.sudo().search_count([
            ("user_id", "=", user.id), ("state", "=", "pending")]))

    @api.model
    def submit(self, user, motivation=None):
        """Crée une demande pending pour `user` (idempotent : refuse un doublon).
        No-op si l'utilisateur est déjà organisateur."""
        if user.has_group(_GROUP):
            raise UserError(_("Vous êtes déjà organisateur."))
        if self._has_pending(user):
            raise UserError(_("Une demande est déjà en attente."))
        return self.sudo().create({
            "user_id": user.id,
            "motivation": (motivation or "").strip() or False,
        })

    # ── Actions modérateur ────────────────────────────────────────────────────

    def action_approve(self):
        group = self.env.ref(_GROUP)
        for rec in self:
            if rec.state != "pending":
                raise UserError(_("Seule une demande en attente peut être approuvée."))
            rec.user_id.sudo().write({"group_ids": [(4, group.id)]})
            rec.sudo().write({
                "state": "approved",
                "reviewer_id": self.env.user.id,
                "reviewed_at": fields.Datetime.now(),
            })
            rec._notify_requester(approved=True)
        return True

    def action_reject(self):
        for rec in self:
            if rec.state != "pending":
                raise UserError(_("Seule une demande en attente peut être refusée."))
            rec.sudo().write({
                "state": "rejected",
                "reviewer_id": self.env.user.id,
                "reviewed_at": fields.Datetime.now(),
            })
            rec._notify_requester(approved=False)
        return True

    def _notify_requester(self, approved):
        """Notifie le demandeur in-app si le module de notifications est présent
        (dépendance optionnelle — no-op sinon ; le statut est visible au portail)."""
        self.ensure_one()
        if "club_social_profile.notification" not in self.env:
            return
        Notification = self.env["club_social_profile.notification"]
        valid = {code for code, _lbl in Notification._fields["type"].selection}
        # Réutilise un type générique s'il existe ; sinon on s'abstient.
        notif_type = "event_registration" if "event_registration" in valid else None
        if not notif_type:
            return
        body = (_("Ta demande pour devenir organisateur a été approuvée.")
                if approved else
                _("Ta demande pour devenir organisateur a été refusée."))
        Notification.sudo()._notify(
            user_id=self.user_id.id,
            actor_id=self.reviewer_id.id or self.env.user.id,
            notif_type=notif_type,
            body=body,
            url="/my/events" if approved else "/my",
        )
