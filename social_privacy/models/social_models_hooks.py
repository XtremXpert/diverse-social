from odoo import models, api


class SocialBasePost(models.Model):
    _inherit = 'social_base.post'

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        # Log reads are harder to hook; writes are easier to track at API level
        return records

    def write(self, vals):
        res = super().write(vals)
        for post in self:
            self.env['social_privacy.access_log'].sudo().create({
                'target_user_id': post.author_id.id,
                'model_name': self._name,
                'record_id': post.id,
                'action': 'write',
                'reason': 'Post updated via write',
            })
        return res

    def unlink(self):
        for post in self:
            self.env['social_privacy.access_log'].sudo().create({
                'target_user_id': post.author_id.id,
                'model_name': self._name,
                'record_id': post.id,
                'action': 'delete',
                'reason': 'Post deleted',
            })
        return super().unlink()


# SocialMessagingMessage hook removed: _inherit on social_messaging.message
# fails registry resolution when social_messaging is absent. social_messaging
# a été retiré au profit de Discuss (social_messaging_discuss). Réintroduire via
# un bridge module si un suivi Loi 25 des messages Discuss devient nécessaire.


# SocialNegotiation hook removed: _inherit on social_negotiation.negotiation
# fails registry resolution when the optional social_negotiation module is
# absent. Re-introduce inside a bridge module (social_privacy_negotiation,
# auto_install on both modules) when negotiation tracking is needed for
# Loi 25 compliance in a deployment that ships social_negotiation.
