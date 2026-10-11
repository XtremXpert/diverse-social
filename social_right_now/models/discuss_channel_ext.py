from odoo import fields, models, _
from odoo.exceptions import UserError


class DiscussChannel(models.Model):
    """Branche « Disponible maintenant » sur la messagerie :

    - exception à la politique de contact (Phase 1) : on peut écrire à une
      personne ayant une session active, même sans connexion ;
    - éphémérité : une conversation née d'une session se ferme à l'expiration
      de celle-ci, sauf si une connexion acceptée existe désormais.
    """
    _inherit = "discuss.channel"

    right_now_session_id = fields.Many2one(
        "social_right_now.session", ondelete="set null", index=True,
        help="Session « Disponible maintenant » ayant ouvert cette conversation.")

    def _smd_message_exception(self, sender, other_user):
        # Exception : contacter une personne « Disponible maintenant ».
        if self.env["social_right_now.session"].sudo()._has_active_session(other_user):
            return True
        return super()._smd_message_exception(sender, other_user)

    def message_post(self, *, message_type="notification", partner_ids=None, **kwargs):
        if message_type not in ("notification", "user_notification"):
            self._srn_assert_right_now_open()
        return super().message_post(
            message_type=message_type, partner_ids=partner_ids, **kwargs)

    def _srn_assert_right_now_open(self):
        """Sur un canal né d'une session expirée, l'écriture est fermée sauf si
        une connexion acceptée existe désormais entre les deux membres."""
        sender = self._smd_blocking_user()
        if not sender:
            return
        Conn = self.env["club_social_profile.connection"].sudo()
        for channel in self:
            session = channel.right_now_session_id
            if not session or channel.channel_type != "chat":
                continue
            if session._is_active():
                continue
            others = channel.sudo().channel_member_ids.partner_id.filtered(
                lambda p: p != sender.partner_id)
            for other_partner in others:
                other_user = other_partner.user_ids[:1]
                if not other_user:
                    continue
                if (Conn.is_connected(sender, other_user)
                        or Conn.is_connected(other_user, sender)):
                    continue
                raise UserError(_(
                    "Cette conversation « Disponible maintenant » est terminée. "
                    "Envoyez une demande de connexion pour continuer à discuter."))
