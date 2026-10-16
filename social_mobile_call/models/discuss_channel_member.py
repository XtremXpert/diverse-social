from odoo import models


class DiscussChannelMember(models.Model):
    _inherit = 'discuss.channel.member'

    def _join_sfu(self, ice_servers=None, force=False):
        """Un appel déjà passé par le SFU y reste.

        Sous trois participants, Odoo repasse l'appel en pair-à-pair à chaque arrivée (il vide
        ``sfu_channel_uuid``). L'application ne parle qu'au SFU : si un membre la rejoignait depuis
        le site, il partirait en pair-à-pair et les deux ne s'entendraient plus. Le canal SFU est
        libéré par Odoo quand le dernier participant quitte l'appel."""
        channel = self.channel_id
        if channel.sfu_channel_uuid and channel.sfu_server_url:
            force = True
        return super()._join_sfu(ice_servers=ice_servers, force=force)
