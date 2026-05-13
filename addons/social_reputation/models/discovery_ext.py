from odoo import models, fields, api, _


class DiscoveryCriteria(models.Model):
    _inherit = 'social_discovery.criteria'

    require_vouched = fields.Boolean(
        'Vouched Members Only',
        help='Only show profiles that have at least one active sponsor.',
    )

    @api.depends('require_vouched')
    def _compute_result_count(self):
        super()._compute_result_count()

    def _find_profiles(self):
        profiles = super()._find_profiles()
        if self.require_vouched:
            profiles = profiles.filtered(lambda p: p.is_vouched)
        return profiles
