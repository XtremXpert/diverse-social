from odoo import _, api, models


class SocialStory(models.Model):
    _inherit = 'social_story.story'

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        Notif = self.env['club_social_profile.notification']
        for story in records:
            connections = self.env['club_social_profile.connection'].search([
                ('user_id', '=', story.author_id.id),
                ('state', '=', 'accepted'),
            ]).mapped('connected_user_id')
            for user in connections:
                Notif._notify(
                    user_id=user.id,
                    actor_id=story.author_id.id,
                    notif_type='story_new',
                    body=_('%s published a new story.', story.author_id.name),
                    ref_model='social_story.story',
                    ref_id=story.id,
                )
        return records
