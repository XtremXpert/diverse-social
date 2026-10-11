from datetime import timedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError


DURATION_HOURS = {"1h": 1, "2h": 2, "4h": 4}


class RightNowSession(models.Model):
    """Session « Disponible maintenant » : borne temporelle explicite pendant
    laquelle un membre est joignable par tous (exception à la politique de
    contact) et visible sur le tableau /right-now."""

    _name = "social_right_now.session"
    _description = "Session « Disponible maintenant »"
    _order = "expires_at desc"

    user_id = fields.Many2one(
        "res.users", required=True, ondelete="cascade", index=True)
    partner_id = fields.Many2one(related="user_id.partner_id", store=True)
    started_at = fields.Datetime(default=fields.Datetime.now, required=True)
    duration = fields.Selection(
        [("1h", "1 heure"), ("2h", "2 heures"), ("4h", "4 heures")],
        default="1h", required=True)
    expires_at = fields.Datetime(
        compute="_compute_expires_at", store=True, index=True)
    note = fields.Char(
        string="Intention", translate=False,
        help="Message court affiché sur le tableau (modéré a posteriori).")
    state = fields.Selection(
        [("active", "Active"), ("expired", "Expirée")],
        compute="_compute_state", search="_search_state", default="active")
    channel_ids = fields.Many2many(
        "discuss.channel", "social_right_now_channel_rel",
        "session_id", "channel_id",
        help="Conversations ouvertes grâce à cette session.")

    @api.depends("started_at", "duration")
    def _compute_expires_at(self):
        for s in self:
            base = s.started_at or fields.Datetime.now()
            s.expires_at = base + timedelta(hours=DURATION_HOURS.get(s.duration, 1))

    @api.depends("expires_at")
    def _compute_state(self):
        now = fields.Datetime.now()
        for s in self:
            s.state = "expired" if (s.expires_at and s.expires_at <= now) else "active"

    def _is_active(self):
        self.ensure_one()
        return bool(self.expires_at and self.expires_at > fields.Datetime.now())

    def _search_state(self, operator, value):
        now = fields.Datetime.now()
        if operator not in ("=", "!=") or value not in ("active", "expired"):
            raise UserError(_("Filtre d'état non supporté."))
        is_active = (value == "active") == (operator == "=")
        return [("expires_at", ">", now)] if is_active else [("expires_at", "<=", now)]

    # ── API ───────────────────────────────────────────────────────────────────

    @api.model
    def _active_domain(self):
        return [("expires_at", ">", fields.Datetime.now())]

    @api.model
    def _has_active_session(self, user):
        """True si `user` a une session active (utilisé comme exception à la
        politique de contact de la messagerie)."""
        if not user:
            return False
        return bool(self.sudo().search_count(
            self._active_domain() + [("user_id", "=", user.id)], limit=1))

    @api.model
    def _get_active_for(self, user):
        return self.sudo().search(
            self._active_domain() + [("user_id", "=", user.id)], limit=1)

    @api.model
    def activate(self, duration="1h", note=None):
        """Active (ou prolonge) la session de l'utilisateur courant. Une seule
        session active par personne : on réutilise l'existante en la relançant."""
        if duration not in DURATION_HOURS:
            duration = "1h"
        user = self.env.user
        existing = self._get_active_for(user)
        vals = {
            "duration": duration,
            "started_at": fields.Datetime.now(),
            "note": (note or "").strip()[:120] or False,
        }
        if existing:
            existing.write(vals)
            session = existing
        else:
            session = self.sudo().create(dict(vals, user_id=user.id))
        session._broadcast("right_now_on")
        return session

    def deactivate(self):
        """Termine la session immédiatement et ferme ses conversations."""
        for session in self:
            session._close_channels()
            session._broadcast("right_now_off")
            # started_at dans le passé lointain → expires_at < now → expirée.
            session.sudo().write({
                "started_at": fields.Datetime.now() - timedelta(hours=5),
                "duration": "1h",
            })

    def _close_channels(self):
        """Marque les conversations de la session comme fermées (la garde
        d'écriture est dans discuss.channel.message_post)."""
        # Rien à écrire : la fermeture est dérivée de l'état de la session.
        # Méthode conservée comme point d'extension (ex. message système).
        return True

    def _broadcast(self, event):
        """Notifie le canal du tableau pour rafraîchir en temps réel."""
        self.ensure_one()
        self.env["bus.bus"]._sendone(
            "social_right_now", "right_now_update",
            {"event": event, "user_id": self.user_id.id})

    @api.model
    def cron_expire_sessions(self):
        """Ferme les conversations des sessions fraîchement expirées. Idempotent :
        la garde d'écriture ne dépend pas du cron, celui-ci sert au broadcast et
        au nettoyage futur."""
        just_expired = self.sudo().search([
            ("expires_at", "<=", fields.Datetime.now()),
            ("expires_at", ">", fields.Datetime.now() - timedelta(hours=1)),
        ])
        for session in just_expired:
            session._broadcast("right_now_off")
        return True
