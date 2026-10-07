import json

from odoo import api, models


class PwaPushService(models.AbstractModel):
    """Web-push enqueue service.

    Thin layer over the standard mail.push queue. Keeps the payload narrow
    on purpose: a constant title + body, regardless of the originating
    notification. The privacy contract is that the lock screen never leaks
    who or what triggered the push. Delivery itself (encryption, VAPID,
    retries, dead-device cleanup) is the standard mail cron's job.
    """
    _name = 'social_pwa.push_service'
    _description = 'Web Push Delivery Service'

    @api.model
    def _generic_payload(self):
        get = self.env['ir.config_parameter'].sudo().get_str
        return {
            'title': get('social_pwa.push_title', 'MétéoMédia'),
            'body': get('social_pwa.push_body', 'Nouvelle activité — ouvrez l\'app pour voir.'),
        }

    @api.model
    def enqueue_for_users(self, user_ids):
        """Queue one generic push per device registered by the given users.

        Returns the number of queued pushes (0 when nobody has a device).
        """
        users = self.env['res.users'].sudo().browse(user_ids)
        devices = self.env['mail.push.device'].sudo().search([
            ('partner_id', 'in', users.partner_id.ids),
        ])
        if not devices:
            return 0
        payload = json.dumps(self._generic_payload())
        self.env['mail.push'].sudo().create([
            {'mail_push_device_id': device.id, 'payload': payload}
            for device in devices
        ])
        self.env.ref('mail.ir_cron_web_push_notification')._trigger()
        return len(devices)
