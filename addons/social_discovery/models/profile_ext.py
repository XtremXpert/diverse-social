from odoo import models, fields, api


class ClubSocialProfile(models.Model):
    _inherit = 'club_social_profile.profile'

    discovery_criteria_ids = fields.One2many(
        'social_discovery.criteria', 'profile_id', string='Saved Searches',
    )
    discovery_criteria_count = fields.Integer(
        compute='_compute_criteria_count',
    )

    @api.depends('discovery_criteria_ids')
    def _compute_criteria_count(self):
        for p in self:
            p.discovery_criteria_count = len(p.discovery_criteria_ids)

    def action_open_discovery(self):
        """Open the default search, or the search list if none."""
        self.ensure_one()
        default = self.discovery_criteria_ids.filtered('is_default')[:1]
        if default:
            return default.action_search()
        return {
            'type': 'ir.actions.act_window',
            'name': 'My Searches',
            'res_model': 'social_discovery.criteria',
            'view_mode': 'list,form',
            'domain': [('profile_id', '=', self.id)],
            'context': {'default_profile_id': self.id},
        }
