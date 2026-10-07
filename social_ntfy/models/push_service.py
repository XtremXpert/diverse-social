import logging

import requests

from odoo import api, models

_logger = logging.getLogger(__name__)


class NtfyPushService(models.AbstractModel):
    """ntfy push delivery service.

    Stateless wrapper around an HTTP POST to a ntfy server. Like social_pwa,
    the payload is deliberately GENERIC — a constant title + body regardless of
    the originating notification — so the lock screen never leaks who or what
    triggered the push. The body stays on our self-hosted server; only a
    content-less wake-up reaches APNS (via the ntfy upstream relay) for iOS.
    """
    _name = 'social_ntfy.push_service'
    _description = 'ntfy Push Delivery Service'

    @api.model
    def _generic_payload(self, topic):
        get = self.env['ir.config_parameter'].sudo().get_str
        base = (get('web.base.url', '') or 'https://www.diverse-cite.com').rstrip('/')
        return {
            'topic': topic,
            'title': get('social_ntfy.push_title', 'Diverse-Cité'),
            'message': get('social_ntfy.push_body',
                           'Nouvelle notification — ouvrez le site pour voir.'),
            'click': base + '/my/dashboard',
            'tags': ['bell'],
        }

    @api.model
    def send_to_user(self, user_id):
        """POST the generic payload to the user's ntfy topic.

        Returns the number of pushes sent (0 or 1). Raises on transport /
        5xx errors so the outbox retries; a 4xx (bad topic/token) returns 0
        and is dropped — retrying a client error never helps.
        """
        get = self.env['ir.config_parameter'].sudo().get_str
        # publish_url lets the server POST to an internal address (e.g. the
        # in-cluster service http://ntfy.ntfy.svc.cluster.local) while members
        # still see/subscribe to the public server_url — avoids hairpin-NAT
        # failures reaching the cluster's own external IP from a pod. Falls
        # back to server_url when unset.
        server = (get('social_ntfy.publish_url', '')
                  or get('social_ntfy.server_url', '') or '').rstrip('/')
        if not server:
            _logger.info('social_ntfy: server_url not configured, push skipped')
            return 0

        profile = self.env['club_social_profile.profile'].sudo().search(
            [('user_id', '=', user_id)], limit=1)
        topic = profile.ntfy_topic if profile else False
        if not topic:
            return 0

        headers = {'Content-Type': 'application/json'}
        token = get('social_ntfy.publish_token', '')
        if token:
            headers['Authorization'] = 'Bearer %s' % token

        # ntfy supports JSON publishing to the root URL with the topic in body.
        resp = requests.post(
            server + '/', json=self._generic_payload(topic),
            headers=headers, timeout=10,
        )
        if resp.status_code < 300:
            return 1
        if resp.status_code >= 500:
            # transient server-side → let the outbox retry
            raise requests.HTTPError(
                'ntfy %s: %s' % (resp.status_code, (resp.text or '')[:120]))
        _logger.warning(
            'social_ntfy: ntfy POST rejected for user %s (HTTP %s): %s',
            user_id, resp.status_code, (resp.text or '')[:200])
        return 0
