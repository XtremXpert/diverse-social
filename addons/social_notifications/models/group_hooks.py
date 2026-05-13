from odoo import _, api, models


class SocialGroupJoinRequest(models.Model):
    _inherit = 'social_group.join_request'

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        Notif = self.env['club_social_profile.notification']
        for req in records:
            admins = req.group_id.admin_ids or req.group_id.creator_id
            for admin in admins:
                Notif._notify(
                    user_id=admin.id,
                    actor_id=req.user_id.id,
                    notif_type='group_join_request',
                    body=_('%s demande à rejoindre le groupe « %s ».',
                           req.user_id.name, req.group_id.name),
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
                body=_('Votre demande d\'adhésion au groupe « %s » a été approuvée.',
                       req.group_id.name),
                ref_model='social_group.group',
                ref_id=req.group_id.id,
            )
        return res
