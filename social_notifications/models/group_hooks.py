from odoo import _, api, models


class SocialGroupJoinRequest(models.Model):
    _inherit = 'social_group.join_request'

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        Notif = self.env['club_social_profile.notification']
        Profile = self.env['club_social_profile.profile']
        for req in records:
            admins = req.group_id.admin_ids or req.group_id.creator_id
            requester_name = Profile._display_name_for_user(req.user_id)
            for admin in admins:
                Notif._notify(
                    user_id=admin.id,
                    actor_id=req.user_id.id,
                    notif_type='group_join_request',
                    body=_('%s requested to join the group "%s".',
                           requester_name, req.group_id.name),
                    ref_model='social_group.group',
                    ref_id=req.group_id.id,
                )
        return records

    def action_approve(self):
        res = super().action_approve()
        Notif = self.env['club_social_profile.notification']
        for req in self:
            Notif._notify(
                user_id=req.user_id.id,
                actor_id=self.env.user.id,
                notif_type='group_join_approved',
                body=_('Your request to join the group "%s" was approved.',
                       req.group_id.name),
                ref_model='social_group.group',
                ref_id=req.group_id.id,
            )
        return res
