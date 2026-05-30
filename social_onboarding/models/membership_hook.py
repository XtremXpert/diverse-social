from odoo import models


class ClubMembershipOnboardingHook(models.Model):
    _inherit = 'club_membership.membership'

    def action_activate(self):
        res = super().action_activate()
        for rec in self:
            if rec.user_id:
                self.env['club_social_profile.profile'].sudo().get_or_create_for_user(rec.user_id)
        return res
