from odoo import api, fields, models


class ClubSocialProfileVisit(models.Model):
    _name = 'club_social_profile.profile_visit'
    _description = 'Profile Visit'
    _order = 'visited_at desc'
    _rec_name = 'visitor_id'

    profile_id = fields.Many2one(
        'club_social_profile.profile', required=True, ondelete='cascade', index=True,
    )
    visitor_id = fields.Many2one('res.users', required=True, ondelete='cascade', index=True)
    visited_at = fields.Datetime(required=True, default=fields.Datetime.now)
    visitor_profile_id = fields.Many2one(
        'club_social_profile.profile',
        compute='_compute_visitor_profile',
        store=True,
    )

    @api.depends('visitor_id')
    def _compute_visitor_profile(self):
        Profile = self.env['club_social_profile.profile']
        for visit in self:
            visit.visitor_profile_id = Profile.search(
                [('user_id', '=', visit.visitor_id.id)], limit=1
            )
