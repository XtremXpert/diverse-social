import json
import logging

from odoo import api, models, _

_logger = logging.getLogger(__name__)

# Soft-import: pywebpush isn't critical to module loading. Deployments
# that haven't installed it yet log a warning when a push is attempted
# instead of crashing the request that created the notification.
try:
    from pywebpush import WebPusher, WebPushException
    PYWEBPUSH_AVAILABLE = True
except ImportError:
    WebPusher = None
    WebPushException = Exception
    PYWEBPUSH_AVAILABLE = False


class PwaPushService(models.AbstractModel):
    """Web-push delivery service.

    Stateless wrapper around pywebpush. Keeps the payload narrow on
    purpose: a constant title + body, regardless of the originating
    notification. The privacy contract is that the lock screen never
    leaks who or what triggered the push.
    """
    _name = 'social_pwa.push_service'
    _description = 'Web Push Delivery Service'

    @api.model
    def _vapid_claims(self):
        """Return the JWT claim block VAPID requires.

        `sub` must be a mailto: URL or an https URL; pywebpush rejects
        anything else. We derive it from the system parameter — failing
        loudly when missing is better than sending requests with a bogus
        sub that the push service silently drops.
        """
        get = self.env['ir.config_parameter'].sudo().get_param
        sub = get('social_pwa.vapid_sub', '')
        if not sub:
            return None
        return {'sub': sub}

    @api.model
    def _generic_payload(self):
        get = self.env['ir.config_parameter'].sudo().get_param
        return {
            'title': get('social_pwa.push_title', 'MétéoMédia'),
            'body': get('social_pwa.push_body', 'Nouvelle activité — ouvrez l\'app pour voir.'),
        }

    @api.model
    def send_to_user(self, user_id):
        """Push the generic payload to every subscription registered for user_id.

        Dead subscriptions (HTTP 404/410 from the push service) are removed
        from the table. Other failures are logged and the subscription is
        kept so a transient outage doesn't unsubscribe everyone.
        """
        if not PYWEBPUSH_AVAILABLE:
            _logger.info('social_pwa: pywebpush not installed, push skipped for user %s', user_id)
            return 0

        get = self.env['ir.config_parameter'].sudo().get_param
        private_key = get('social_pwa.vapid_private_key', '')
        if not private_key:
            _logger.info('social_pwa: VAPID private key not configured, push skipped')
            return 0

        claims = self._vapid_claims()
        if not claims:
            _logger.warning('social_pwa.vapid_sub is not set; push services will reject our JWTs')
            return 0

        subs = self.env['social_pwa.subscription'].sudo().search([
            ('user_id', '=', user_id),
        ])
        if not subs:
            return 0

        payload = json.dumps(self._generic_payload())
        sent = 0
        dead_subs = self.env['social_pwa.subscription']
        for sub in subs:
            subscription_info = {
                'endpoint': sub.endpoint,
                'keys': {'p256dh': sub.p256dh, 'auth': sub.auth},
            }
            try:
                pusher = WebPusher(subscription_info)
                pusher.send(
                    data=payload,
                    vapid_private_key=private_key,
                    vapid_claims=claims,
                    ttl=600,
                )
                sent += 1
            except WebPushException as exc:
                status = getattr(exc.response, 'status_code', None)
                if status in (404, 410):
                    dead_subs |= sub
                else:
                    _logger.warning('social_pwa: push failed for sub %s (HTTP %s)', sub.id, status)
            except Exception:
                _logger.exception('social_pwa: unexpected push error for sub %s', sub.id)

        if dead_subs:
            _logger.info('social_pwa: removing %d dead subscription(s)', len(dead_subs))
            dead_subs.unlink()

        return sent
