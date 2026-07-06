from odoo import _, api, models


class EventRegistration(models.Model):
    _inherit = 'event.registration'

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        Notif = self.env['club_social_profile.notification']
        for reg in records:
            organizer = reg.event_id.organizer_user_id
            if not organizer or not reg.partner_id:
                continue
            registrant_user = self.env['res.users'].search(
                [('partner_id', '=', reg.partner_id.id)], limit=1
            )
            actor_id = registrant_user.id if registrant_user else self.env.user.id
            Notif._notify(
                user_id=organizer.id,
                actor_id=actor_id,
                notif_type='event_registration',
                body=_('%s registered for your event "%s".',
                       self.env['club_social_profile.profile']._display_name_for_user(registrant_user)
                       if registrant_user else reg.partner_id.name,
                       reg.event_id.name),
                ref_model='event.event',
                ref_id=reg.event_id.id,
            )
        return records
