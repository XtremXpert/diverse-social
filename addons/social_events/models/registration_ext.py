from odoo import models, api, _
from odoo.exceptions import UserError


class EventRegistration(models.Model):
    _inherit = 'event.registration'

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for reg in records:
            if reg.event_id.social_visibility \
                    and not reg.event_id._check_social_access(self.env.user):
                raise UserError(_(
                    'You are not allowed to register for "%s".',
                    reg.event_id.name,
                ))
        return records
