from odoo import api, fields, models


class SocialGroup(models.Model):
    """Conversation de groupe Discuss d'un groupe : créée avec ses premiers membres, mêmes membres
    ensuite (arrivées et départs), même nom. Elle se lit sur le site (Discuss) et dans l'application
    mobile, comme les conversations de relation."""
    _inherit = 'social_group.group'

    channel_id = fields.Many2one('discuss.channel', "Conversation", readonly=True, ondelete='set null', copy=False)

    @api.model_create_multi
    def create(self, vals_list):
        groups = super().create(vals_list)
        groups._sync_channel()
        return groups

    def write(self, vals):
        res = super().write(vals)
        if 'member_ids' in vals:
            self._sync_channel()
        if 'name' in vals:
            for group in self.filtered('channel_id'):
                group.channel_id.sudo().name = group.name
        return res

    def unlink(self):
        # Groupe supprimé : la conversation n'a plus de membres (l'historique reste aux administrateurs).
        self.channel_id.sudo().channel_member_ids.unlink()
        return super().unlink()

    def _sync_channel(self):
        Channel = self.env['discuss.channel'].sudo()
        for group in self.sudo():
            users = group.member_ids.filtered('active')
            if not group.channel_id:
                if not users:
                    continue
                group.channel_id = Channel._create_group(users, name=group.name)
            # Seulement les membres du groupe (``_create_group`` ajoute aussi l'utilisateur courant).
            partners = users.partner_id
            group.channel_id.channel_member_ids.filtered(lambda m: m.partner_id not in partners).unlink()
            missing = partners - group.channel_id.channel_member_ids.partner_id
            if missing:
                group.channel_id._add_members(partners=missing, post_joined_message=False)
