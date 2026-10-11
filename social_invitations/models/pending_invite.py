from datetime import timedelta

from odoo import api, fields, models


class PendingInvite(models.Model):
    """Invitation groupe/cercle en attente pour un courriel PAS ENCORE membre.

    Quand la personne s'inscrit (res.users créé avec ce login), l'invitation
    in-site correspondante est matérialisée automatiquement — elle l'accepte
    ensuite comme n'importe quelle invitation (pas d'ajout silencieux).
    """
    _name = "social_invitations.pending"
    _description = "Invitation en attente (courriel non-membre)"
    _order = "create_date desc"

    email = fields.Char(required=True, index=True)
    inviter_user_id = fields.Many2one("res.users", required=True, ondelete="cascade")
    group_id = fields.Many2one("social_group.group", ondelete="cascade")
    circle_id = fields.Many2one("social_circles.circle", ondelete="cascade")
    state = fields.Selection([
        ("pending", "Pending"),
        ("consumed", "Consumed"),
        ("expired", "Expired"),
    ], default="pending", required=True, index=True)
    expires_at = fields.Datetime(
        default=lambda self: fields.Datetime.now() + timedelta(days=30))

    @api.model
    def _capture(self, email, inviter, group=None, circle=None):
        """Enregistre l'intention pour un courriel inconnu."""
        return self.sudo().create({
            "email": (email or "").strip().lower(),
            "inviter_user_id": inviter.id,
            "group_id": group.id if group else False,
            "circle_id": circle.id if circle else False,
        })

    @api.model
    def _consume_for_users(self, users):
        """Matérialise les invitations en attente pour les users fraîchement
        créés (appelé depuis res.users.create)."""
        for user in users:
            login = (user.login or "").strip().lower()
            if not login:
                continue
            pendings = self.sudo().search([
                ("email", "=", login),
                ("state", "=", "pending"),
                ("expires_at", ">", fields.Datetime.now()),
            ])
            for p in pendings:
                p._materialize(user)

    def _materialize(self, user):
        self.ensure_one()
        try:
            if self.group_id and self.group_id.exists():
                self.env["social_group.invitation"].sudo().create({
                    "group_id": self.group_id.id,
                    "invitee_user_id": user.id,
                    "inviter_user_id": self.inviter_user_id.id,
                })
            elif self.circle_id and self.circle_id.exists():
                self.env["social_circles.invitation"].sudo().create({
                    "circle_id": self.circle_id.id,
                    "invitee_user_id": user.id,
                    "inviter_user_id": self.inviter_user_id.id,
                })
        except Exception:
            # Doublon / déjà membre : on consomme quand même, pas d'échec bloquant.
            pass
        self.sudo().write({"state": "consumed"})

    @api.model
    def cron_expire(self):
        stale = self.sudo().search([
            ("state", "=", "pending"),
            ("expires_at", "<", fields.Datetime.now()),
        ])
        if stale:
            stale.write({"state": "expired"})
        return len(stale)
