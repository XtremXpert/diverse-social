from odoo import models

# Au plus ce nombre de personnes impliquées : la dernière personne seule est raccrochée.
ALONE_HANGUP_MAX_INVOLVED = 2


class DiscussChannel(models.Model):
    """Fin d'un appel quand il ne reste qu'une personne.

    Odoo laisse la dernière personne seule dans l'appel jusqu'à ce qu'elle raccroche. Quand
    l'appel n'a jamais impliqué plus de deux personnes (participants et invités), il n'y a
    plus personne à attendre : le serveur termine sa session. On ne vérifie qu'au départ de
    quelqu'un (session fermée ou expirée, invitation refusée ou annulée), jamais pendant
    qu'un membre rejoint l'appel."""
    _inherit = 'discuss.channel'

    def _social_call_open_history(self):
        self.ensure_one()
        # sudo - discuss.call.history : lecture et suivi des personnes impliquées.
        return self.env['discuss.call.history'].sudo().search(
            [('channel_id', '=', self.id), ('end_dt', '=', False)], order='id desc', limit=1)

    def _social_call_note_involved(self, members):
        for channel in self:
            channel_members = members.filtered(lambda m: m.channel_id == channel)
            history = channel._social_call_open_history() if channel_members else None
            if history:
                history.involved_member_ids = [(4, member.id) for member in channel_members]

    def _social_call_check_alone(self):
        if self.env.context.get('social_call_joining') or self.env.context.get('social_call_checking'):
            return
        Session = self.env['discuss.channel.rtc.session'].sudo()
        Member = self.env['discuss.channel.member'].sudo()
        for channel in self:
            sessions = Session.search([('channel_id', '=', channel.id)])
            if len(sessions) != 1:
                continue
            if Member.search_count([('channel_id', '=', channel.id), ('rtc_inviting_session_id', '!=', False)]):
                continue
            history = channel._social_call_open_history()
            if not history or len(history.involved_member_ids) > ALONE_HANGUP_MAX_INVOLVED:
                continue
            # Avant la fin de session : le site remplace l'avertissement d'Odoo
            # (« déconnecté par le serveur ») par un message normal.
            sessions._bus_send('social_calling_discuss/ended_alone', {'sessionId': sessions.id})
            sessions.with_context(social_call_checking=True).unlink()

    def _rtc_cancel_invitations(self, member_ids=None):
        res = super()._rtc_cancel_invitations(member_ids=member_ids)
        self._social_call_check_alone()
        return res
