from odoo import api, fields, models


class EventEvent(models.Model):
    _inherit = 'event.event'

    lodging_single_count = fields.Integer(
        string="Lits simples",
        compute='_compute_lodging_counts',
    )
    lodging_double_count = fields.Integer(
        string="Lits doubles",
        compute='_compute_lodging_counts',
    )
    lodging_total_count = fields.Integer(
        string="Total chambres",
        compute='_compute_lodging_counts',
    )

    @api.depends('registration_ids.lodging_type', 'registration_ids.state')
    def _compute_lodging_counts(self):
        for event in self:
            confirmed = event.registration_ids.filtered(
                lambda r: r.state not in ('cancel',)
            )
            event.lodging_single_count = len(
                confirmed.filtered(lambda r: r.lodging_type == 'single')
            )
            event.lodging_double_count = len(
                confirmed.filtered(lambda r: r.lodging_type == 'double')
            )
            event.lodging_total_count = (
                event.lodging_single_count + event.lodging_double_count
            )
