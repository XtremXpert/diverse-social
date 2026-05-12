from odoo import models, fields


class SocialPost(models.Model):
    """Étend social_base.post avec le support des groupes."""
    _inherit = 'social_base.post'

    group_id = fields.Many2one('social_group.group', 'Group', ondelete='cascade', index=True)
