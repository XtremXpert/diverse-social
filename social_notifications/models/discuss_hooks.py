from odoo import _, models


class DiscussChannel(models.Model):
    """Notifie le destinataire d'un nouveau message Discuss (chat 1:1).

    La messagerie a migré vers discuss.channel ; on émet la même notification
    réseau (« cloche ») que pour l'ancienne social_messaging.message, via le type
    `new_message`. Scope strict aux chats 1:1 → pas de bruit sur les canaux
    d'équipe / livechat internes.
    """
    _inherit = 'discuss.channel'

    def message_post(self, *, message_type="notification", partner_ids=None, **kwargs):
        message = super().message_post(
            message_type=message_type, partner_ids=partner_ids, **kwargs)
        # Pas de notif pour les messages système (join, etc.).
        if message_type not in ("notification", "user_notification"):
            self._sn_notify_new_message()
        return message

    def _sn_notify_new_message(self):
        author = self.env.user
        if not author or author._is_public():
            return
        Notif = self.env['club_social_profile.notification']
        for channel in self:
            if channel.channel_type != 'chat':
                continue
            others = channel.sudo().channel_member_ids.partner_id.filtered(
                lambda p: p != author.partner_id)
            for partner in others:
                target = partner.user_ids[:1]
                if not target:
                    continue
                Notif._notify(
                    user_id=target.id,
                    actor_id=author.id,
                    notif_type='new_message',
                    body=_('%s sent you a message.', author.name),
                    ref_model='discuss.channel',
                    ref_id=channel.id,
                    url='/discuss/channel/%s' % channel.id,
                )
