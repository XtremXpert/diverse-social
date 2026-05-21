from odoo import models, fields, api


class SocialReaction(models.Model):
    """Extends social_base.reaction with story support."""
    _inherit = 'social_base.reaction'

    story_id = fields.Many2one('social_story.story', 'Story', ondelete='cascade', index=True)

    @api.depends('post_id', 'comment_id', 'story_id')
    def _compute_target(self):
        for reaction in self:
            if reaction.post_id:
                reaction.target_id = reaction.post_id.id
                reaction.target_model = 'social_base.post'
            elif reaction.comment_id:
                reaction.target_id = reaction.comment_id.id
                reaction.target_model = 'social_base.comment'
            elif reaction.story_id:
                reaction.target_id = reaction.story_id.id
                reaction.target_model = 'social_story.story'
            else:
                reaction.target_id = 0
                reaction.target_model = False
