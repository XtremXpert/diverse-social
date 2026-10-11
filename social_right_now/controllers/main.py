from odoo import http, fields
from odoo.http import request
from odoo.exceptions import AccessDenied


class RightNow(http.Controller):
    """Tableau « Disponible maintenant » et actions de session.

    Réservé aux membres du réseau (auth='user' + groupe social vérifié).
    """

    def _require_social_user(self):
        user = request.env.user
        if not user or not user.has_group("social_base.group_social_user"):
            raise AccessDenied()
        return user

    def _visible_sessions(self, viewer):
        """Sessions actives visibles par `viewer` : exclut soi-même, les paires
        bloquées, les profils en mode discret (panic) et les shadow-bannis."""
        Session = request.env["social_right_now.session"].sudo()
        Block = request.env["social_safety.block"].sudo()
        Profile = request.env["club_social_profile.profile"].sudo()
        sessions = Session.search(
            Session._active_domain() + [("user_id", "!=", viewer.id)],
            order="started_at desc")

        cards = []
        now = fields.Datetime.now()
        for s in sessions:
            other = s.user_id
            if Block.is_blocked(viewer, other):
                continue
            profile = Profile.search([("user_id", "=", other.id)], limit=1)
            if not profile:
                continue
            if getattr(profile, "panic_mode", False):
                continue
            if getattr(profile, "is_shadow_banned", False):
                continue
            remaining = s.expires_at - now
            minutes = max(0, int(remaining.total_seconds() // 60))
            cards.append({
                "user": other,
                "profile": profile,
                "display_name": Profile._display_name_for_user(other),
                "note": s.note or "",
                "minutes_left": minutes,
            })
        return cards

    @http.route("/right-now", type="http", auth="user", website=True, sitemap=False)
    def right_now_board(self, **kw):
        viewer = self._require_social_user()
        Session = request.env["social_right_now.session"].sudo()
        my_session = Session._get_active_for(viewer)
        return request.render("social_right_now.board", {
            "cards": self._visible_sessions(viewer),
            "my_session": my_session,
            "page_name": "right_now",
        })

    @http.route("/right-now/activate", type="http", auth="user",
                methods=["POST"], website=True, csrf=True)
    def right_now_activate(self, duration="1h", note=None, **kw):
        self._require_social_user()
        request.env["social_right_now.session"].activate(
            duration=duration, note=note)
        return request.redirect("/right-now")

    @http.route("/right-now/deactivate", type="http", auth="user",
                methods=["POST"], website=True, csrf=True)
    def right_now_deactivate(self, **kw):
        viewer = self._require_social_user()
        session = request.env["social_right_now.session"].sudo()._get_active_for(viewer)
        if session:
            session.deactivate()
        return request.redirect("/right-now")

    @http.route("/right-now/message/<int:user_id>", type="http", auth="user",
                website=True, sitemap=False)
    def right_now_message(self, user_id, **kw):
        viewer = self._require_social_user()
        other = request.env["res.users"].sudo().browse(user_id)
        if not other.exists() or other.id == viewer.id or not other.partner_id:
            return request.redirect("/right-now")

        # Blocage prioritaire.
        if request.env["social_safety.block"].sudo().is_blocked(viewer, other):
            raise AccessDenied()

        Session = request.env["social_right_now.session"].sudo()
        session = Session._get_active_for(other)
        if not session:
            # Session expirée entre l'affichage et le clic : retour au tableau.
            return request.redirect("/right-now")

        # Ne pas transformer une conversation préexistante en éphémère.
        existed = request.env["discuss.channel"]._smd_chat_exists_with(
            [other.partner_id.id])
        channel = request.env["discuss.channel"].sudo()._get_or_create_chat(
            [other.partner_id.id])
        if not existed and not channel.right_now_session_id:
            channel.sudo().write({"right_now_session_id": session.id})
        return request.redirect("/discuss/channel/%s" % channel.id)
