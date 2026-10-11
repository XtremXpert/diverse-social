import logging

from werkzeug.exceptions import Forbidden, NotFound

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class SocialInvitations(http.Controller):
    """Inviter à un groupe/cercle depuis une fiche ou par courriel."""

    def _user(self):
        user = request.env.user
        if not user or not user.has_group("social_base.group_social_user"):
            raise Forbidden()
        return user

    def _blocked(self, other):
        return request.env["social_safety.block"].sudo().is_blocked(
            request.env.user, other)

    def _is_connection(self, me, other):
        Conn = request.env["club_social_profile.connection"].sudo()
        return Conn.is_connected(me, other) or Conn.is_connected(other, me)

    # ── Depuis la fiche : invitation in-site ──────────────────────────────────

    @http.route("/invite/group/<int:group_id>/<int:user_id>", type="http",
                auth="user", methods=["POST"], website=True, csrf=True)
    def invite_group(self, group_id, user_id, **kw):
        me = self._user()
        group = request.env["social_group.group"].sudo().browse(group_id).exists()
        target = request.env["res.users"].sudo().browse(user_id).exists()
        if not group or not target:
            raise NotFound()
        if not group.can_invite(me) or self._blocked(target):
            raise Forbidden()
        self._safe_create("social_group.invitation", {
            "group_id": group.id,
            "invitee_user_id": target.id,
            "inviter_user_id": me.id,
        })
        return request.redirect("/profile/%s?invited=1" % user_id)

    @http.route("/invite/circle/<int:circle_id>/<int:user_id>", type="http",
                auth="user", methods=["POST"], website=True, csrf=True)
    def invite_circle(self, circle_id, user_id, **kw):
        me = self._user()
        circle = request.env["social_circles.circle"].sudo().browse(circle_id).exists()
        target = request.env["res.users"].sudo().browse(user_id).exists()
        if not circle or not target:
            raise NotFound()
        # Cercle = connexions acceptées seulement (décision produit). Depuis la
        # fiche d'un non-connecté, le cercle n'est pas proposé ; on refuse aussi
        # côté serveur.
        if (circle.profile_id.user_id != me or self._blocked(target)
                or not self._is_connection(me, target)):
            raise Forbidden()
        self._safe_create("social_circles.invitation", {
            "circle_id": circle.id,
            "invitee_user_id": target.id,
            "inviter_user_id": me.id,
        })
        return request.redirect("/profile/%s?invited=1" % user_id)

    # ── Par courriel : interception des membres existants ─────────────────────

    @http.route("/invite/email", type="http", auth="user",
                methods=["POST"], website=True, csrf=True)
    def invite_email(self, email=None, group_id=None, circle_id=None, **kw):
        """Invite par courriel. Réponse TOUJOURS identique (« invitation
        envoyée ») : l'inviteur n'apprend pas si l'adresse est déjà membre."""
        me = self._user()
        email = (email or "").strip().lower()
        group = self._own_group_or_none(me, group_id)
        circle = self._own_circle_or_none(me, circle_id)
        back = self._back_url(group, circle)
        if not email or "@" not in email or (not group and not circle):
            return request.redirect(back + "error=invalid")

        existing = request.env["res.users"].sudo().search(
            [("login", "=", email)], limit=1)
        if existing and existing.has_group("social_base.group_social_user"):
            # INTERCEPTION : invitation in-site, aucun courriel. Pas de reveal.
            if not self._blocked(existing):
                if group:
                    self._safe_create("social_group.invitation", {
                        "group_id": group.id, "invitee_user_id": existing.id,
                        "inviter_user_id": me.id})
                elif circle and self._is_connection(me, existing):
                    # Cercle = connexions seulement, y compris via interception.
                    self._safe_create("social_circles.invitation", {
                        "circle_id": circle.id, "invitee_user_id": existing.id,
                        "inviter_user_id": me.id})
        else:
            # Courriel inconnu : enregistre l'intention + invitation d'inscription.
            # Branche gardée de façon SYMÉTRIQUE à l'interception : un échec ne
            # doit jamais produire une réponse différente (sinon oracle
            # d'appartenance au site).
            try:
                with request.env.cr.savepoint():
                    request.env["social_invitations.pending"]._capture(
                        email, me, group=group, circle=circle)
            except Exception:
                _logger.info("Intention d'invitation non enregistrée pour %s", email)
            self._send_signup_invite(email, me)
        # Réponse identique dans tous les cas (membre / inconnu / bloqué).
        return request.redirect(back + "invited=1")

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _safe_create(self, model, vals):
        """Crée en gérant les doublons/contraintes sans casser la requête."""
        try:
            with request.env.cr.savepoint():
                request.env[model].sudo().create(vals)
        except Exception:
            _logger.info("Invitation %s ignorée (doublon/contrainte)", model)

    def _own_group_or_none(self, me, group_id):
        if not group_id:
            return None
        g = request.env["social_group.group"].sudo().browse(int(group_id)).exists()
        return g if g and g.can_invite(me) else None

    def _own_circle_or_none(self, me, circle_id):
        if not circle_id:
            return None
        c = request.env["social_circles.circle"].sudo().browse(int(circle_id)).exists()
        return c if c and c.profile_id.user_id == me else None

    def _back_url(self, group, circle):
        if group:
            return "/groups/%s?" % group.id
        if circle:
            return "/my/circles?"
        return "/my?"

    def _send_signup_invite(self, email, sponsor):
        """Envoie l'invitation d'inscription via le vouching existant. Best-effort :
        un échec ne casse pas le flux (l'intention reste enregistrée)."""
        try:
            with request.env.cr.savepoint():
                vouch = request.env["social_reputation.vouching"].sudo(
                ).action_invite_email(email, sponsor=sponsor)
                if hasattr(vouch, "action_send_invitation_email"):
                    vouch.action_send_invitation_email()
        except Exception:
            _logger.info("Vouching signup invite non envoyé pour %s", email)
