from odoo import models


class DiscussChannelMember(models.Model):
    _inherit = 'discuss.channel.member'

    def _rtc_join_call(self, store=None, check_rtc_session_ids=None, camera=False):
        # Rejoindre annule sa propre invitation et ferme ses autres sessions avant de créer la
        # nouvelle : l'appel compte un instant une seule personne, sans que personne soit parti.
        return super(DiscussChannelMember, self.with_context(social_call_joining=True))._rtc_join_call(
            store=store, check_rtc_session_ids=check_rtc_session_ids, camera=camera)

    def _rtc_invite_members(self, member_ids=None):
        res = super()._rtc_invite_members(member_ids=member_ids)
        invited = self.env['discuss.channel.member'].sudo().search([
            ('channel_id', '=', self.channel_id.id),
            ('rtc_inviting_session_id', '!=', False),
        ])
        self.channel_id._social_call_note_involved(invited)
        return res
