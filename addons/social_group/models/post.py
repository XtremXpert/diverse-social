from odoo import models, fields


class SocialPost(models.Model):
    """Extends social_base.post with group support."""
    _inherit = 'social_base.post'

    group_id = fields.Many2one('social_group.group', 'Group', ondelete='cascade', index=True)
