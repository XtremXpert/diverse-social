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


class SocialNegotiation(models.Model):
    _inherit = 'social_negotiation.negotiation'

    def unlink(self):
        for neg in self:
            self.env['social_privacy.access_log'].sudo().create({
                'target_user_id': neg.initiator_id.id,
                'model_name': self._name,
                'record_id': neg.id,
                'action': 'delete',
                'reason': 'Negotiation deleted',
            })
        return super().unlink()
