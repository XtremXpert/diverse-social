from odoo import _, models


class SocialProposal(models.Model):
    _inherit = 'social_governance.proposal'

    def action_start_voting(self):
        res = super().action_start_voting()
        # Notifying every social member requires reading res.groups + res.users,
        # which a plain social_user can't do — broadcast as sudo since this is
        # a side-effect that doesn't depend on the caller's visibility.
        Notif = self.env['club_social_profile.notification'].sudo()
        group = self.env.ref('social_base.group_social_user')
        social_users = self.env['res.users'].sudo().search(
            [('all_group_ids', 'in', [group.id])])
        for proposal in self:
            for user in social_users - proposal.author_id:
                Notif._notify(
                    user_id=user.id,
                    actor_id=proposal.author_id.id,
                    notif_type='proposal_voting',
                    body=_('Nouvelle proposition ouverte au vote : "%s"', proposal.name),
                    ref_model='social_governance.proposal',
                    ref_id=proposal.id,
                )
        return res
