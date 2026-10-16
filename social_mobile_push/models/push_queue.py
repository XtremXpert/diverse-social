import datetime
import logging

from odoo import api, fields, models

from . import apns

_logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 5
BATCH = 200
DEFAULT_TOPIC = 'com.diversecite.app'
# Textes discrets : ni nom, ni contenu (l'écran verrouillé est vu par d'autres).
BODIES = {
    'message': "Nouveau message",
    'relation_invite': "Vous êtes invité·e dans une relation",
    'relation_proposal': "Une proposition attend votre accord",
}


class SocialMobilePushQueue(models.Model):
    """Notification à envoyer à un membre. Remplie dans la transaction de l'événement, vidée par
    la tâche planifiée (déclenchée aussitôt) : l'appel à Apple ne ralentit jamais la requête."""
    _name = 'social_mobile.push_queue'
    _description = "Notification iPhone à envoyer"
    _order = 'id'

    user_id = fields.Many2one('res.users', required=True, index=True, ondelete='cascade')
    kind = fields.Selection([(k, k) for k in BODIES], required=True)
    channel_id = fields.Many2one('discuss.channel', ondelete='cascade')
    relation_id = fields.Many2one('social_relation.relation', ondelete='cascade')
    author_id = fields.Many2one('res.users', ondelete='set null')
    state = fields.Selection([('pending', "À envoyer"), ('done', "Traitée")], default='pending', required=True, index=True)
    attempts = fields.Integer(default=0)
    next_try = fields.Datetime(default=fields.Datetime.now, index=True)

    @api.model
    def _enqueue(self, users, kind, channel=None, relation=None, author=None):
        """Met en file une notification par membre. Les messages d'une même conversation non encore
        envoyés n'en donnent qu'une (pas de rafale)."""
        Queue = self.sudo()
        created = False
        for user in users:
            if kind == 'message' and channel and Queue.search_count([
                    ('user_id', '=', user.id), ('kind', '=', 'message'), ('channel_id', '=', channel.id),
                    ('state', '=', 'pending')], limit=1):
                continue
            Queue.create({
                'user_id': user.id, 'kind': kind,
                'channel_id': channel.id if channel else False,
                'relation_id': relation.id if relation else False,
                'author_id': author.id if author else False,
            })
            created = True
        if created:
            cron = self.env.ref('social_mobile_push.cron_dispatch_push', raise_if_not_found=False)
            if cron:
                cron.sudo()._trigger()

    # ── Envoi ────────────────────────────────────────────────────────────────

    @api.model
    def _config(self):
        ICP = self.env['ir.config_parameter'].sudo()
        config = {
            'team_id': ICP.get_str('social_mobile_push.team_id') or '',
            'key_id': ICP.get_str('social_mobile_push.key_id') or '',
            'key': ICP.get_str('social_mobile_push.apns_key') or '',
            'topic': ICP.get_str('social_mobile_push.bundle_id') or DEFAULT_TOPIC,
            'show_sender': ICP.get_bool('social_mobile_push.show_sender'),
        }
        return config if config['team_id'] and config['key_id'] and config['key'] else None

    def _still_relevant(self):
        """Le destinataire doit toujours être membre du réseau, et de la conversation, non muette."""
        self.ensure_one()
        user = self.user_id
        if not user.active or not user.has_group('social_base.group_social_user'):
            return False
        if self.kind == 'message':
            channel = self.channel_id
            if not channel:
                return False
            member = channel.channel_member_ids.filtered(lambda m: m.partner_id == user.partner_id)[:1]
            if not member or (member.mute_until_dt and member.mute_until_dt > fields.Datetime.now()):
                return False
        return True

    def _payload(self, config):
        self.ensure_one()
        user = self.user_id
        body = BODIES[self.kind]
        if self.kind == 'message' and config['show_sender'] and self.author_id:
            body = "Message de %s" % self.env['club_social_profile.profile'].sudo()._display_name_for_user(self.author_id)
        channels = self.env['discuss.channel']._mobile_channels(user)
        members = channels.channel_member_ids.filtered(lambda m: m.partner_id == user.partner_id)
        payload = {'aps': {
            'alert': {'title': "Diverse-Cité", 'body': body},
            'sound': 'default',
            'badge': sum(members.mapped('message_unread_counter')),
        }}
        if self.channel_id:
            payload['aps']['thread-id'] = 'chat-%s' % self.channel_id.id
            payload['chat_id'] = self.channel_id.id
        if self.relation_id:
            payload['relation_id'] = self.relation_id.id
        return payload

    @api.model
    def _http_client(self):
        import httpx  # noqa: PLC0415 - dépendance externe, chargée à l'envoi seulement
        return httpx.Client(http2=True, timeout=10.0)

    @api.model
    def _send(self, client, environment, token, topic, provider_jwt, payload, collapse_id, **options):
        """Point d'appel unique vers Apple (remplacé dans les tests). ``options`` : ``push_type``,
        ``expiration`` (appels)."""
        return apns.post(client, environment, token, topic, provider_jwt, payload, collapse_id, **options)

    @api.model
    def _cron_dispatch(self):
        now = fields.Datetime.now()
        rows = self.sudo().search([('state', '=', 'pending'), ('next_try', '<=', now)], limit=BATCH)
        self.sudo().search([('state', '=', 'done'), ('write_date', '<', now - datetime.timedelta(days=1))]).unlink()
        if not rows:
            return
        config = self._config()
        if not config:
            # Pas de clé APNs (pas encore réglée, ou base neutralisée) : rien ne part.
            rows.write({'state': 'done'})
            return
        Device = self.env['social_mobile.device'].sudo()
        with self._http_client() as client:
            for row in rows:
                if not row._still_relevant():
                    row.state = 'done'
                    continue
                payload = row._payload(config)
                collapse = 'chat-%s' % row.channel_id.id if row.channel_id else None
                retry = False
                for device in Device.search([('user_id', '=', row.user_id.id), ('kind', '=', 'alert')]):
                    outcome = row._deliver(client, device, config, payload, collapse)
                    if outcome == 'stop':
                        return  # configuration refusée par Apple : on garde la file pour plus tard
                    retry = retry or outcome == 'retry'
                if retry and row.attempts + 1 < MAX_ATTEMPTS:
                    row.write({'attempts': row.attempts + 1, 'next_try': now + datetime.timedelta(minutes=2 ** row.attempts)})
                else:
                    row.state = 'done'

    def _deliver(self, client, device, config, payload, collapse, **options):
        """Envoie à un appareil. Retourne ``'ok'``, ``'retry'`` ou ``'stop'``.

        Un appareil ``voip`` reçoit sur le sujet ``<bundle>.voip`` ; ``options`` passe à ``_send``."""
        topic = config['topic'] + ('.voip' if device.kind == 'voip' else '')

        def attempt(environment):
            provider_jwt = apns.provider_token(config['team_id'], config['key_id'], config['key'])
            return self._send(client, environment, device.token, topic, provider_jwt, payload, collapse, **options)

        try:
            status, reason = attempt(device.environment)
            if status == 403 and reason == 'ExpiredProviderToken':
                apns.forget_token(config['team_id'], config['key_id'], config['key'])
                status, reason = attempt(device.environment)
            if status == 400 and reason == 'BadDeviceToken':
                # Jeton d'une app installée par Xcode (sandbox) ou par l'App Store (production) :
                # on essaie l'autre serveur, et on corrige l'appareil si c'était lui.
                other = 'sandbox' if device.environment == 'production' else 'production'
                status, reason = attempt(other)
                if status == 200:
                    device.environment = other
        except Exception:  # noqa: BLE001 - réseau : on réessaiera
            _logger.warning("APNs injoignable", exc_info=True)
            return 'retry'
        if status == 200:
            return 'ok'
        if status == 410 or reason in ('Unregistered', 'BadDeviceToken', 'DeviceTokenNotForTopic'):
            device.unlink()
            return 'ok'
        if status == 403:
            _logger.error("APNs refuse la configuration (%s) : vérifiez l'équipe, la clé et le bundle", reason)
            return 'stop'
        if status == 429 or status >= 500:
            return 'retry'
        _logger.warning("APNs : notification refusée (%s %s)", status, reason)
        return 'ok'
