from odoo import _, api, models


class SocialMessage(models.Model):
    _inherit = 'social_messaging.message'

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        Notif = self.env['club_social_profile.notification']
        for msg in records:
            recipients = msg.thread_id.participant_ids - msg.author_id
            for user in recipients:
                Notif._notify(
                    user_id=user.id,
                    actor_id=msg.author_id.id,
                    notif_type='new_message',
                    body=_('%s sent you a message.', msg.author_id.name),
                    ref_model='social_messaging.thread',
                    ref_id=msg.thread_id.id,
                )
        return records
