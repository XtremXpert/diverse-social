from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    event_login_required = fields.Boolean(
        related='website_id.event_login_required',
        readonly=False,
    )
