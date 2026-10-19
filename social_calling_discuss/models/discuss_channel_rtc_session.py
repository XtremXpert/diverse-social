from odoo import api, models


class DiscussChannelRtcSession(models.Model):
    _inherit = 'discuss.channel.rtc.session'

    @api.model_create_multi
    def create(self, vals_list):
        sessions = super().create(vals_list)
        sessions.channel_id._social_call_note_involved(sessions.channel_member_id)
        return sessions

    def unlink(self):
        channels = self.channel_id
        # Pendant la suppression, Odoo annule les invitations restantes : rien à vérifier tant
        # que ces sessions existent encore.
        res = super(DiscussChannelRtcSession, self.with_context(social_call_checking=True)).unlink()
        channels._social_call_check_alone()
        return res
