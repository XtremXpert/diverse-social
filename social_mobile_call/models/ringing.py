"""Sonnerie des appels sur l'iPhone, application fermée (PushKit puis CallKit).

Odoo invite les autres membres quand un appel commence (``rtc_inviting_session_id``) et annule
l'invitation quand l'appel est rejoint, refusé ou terminé. Chaque invitation part en notification
VoIP « ring » vers les iPhone de l'invité, chaque annulation en « end » : l'iPhone affiche puis
retire l'appel entrant. iOS exige qu'une notification VoIP affiche un appel ; on n'en envoie donc
jamais pour rien (pas de « end » vers l'iPhone qui vient lui-même de répondre ou de refuser).

L'envoi part après la validation de la transaction (``postcommit``), directement vers Apple : une
sonnerie ne peut pas attendre la tâche planifiée. Apple l'abandonne au-delà de ``RING_TTL``.
"""
import logging
import time
import uuid

from odoo import SUPERUSER_ID, api, fields, models

_logger = logging.getLogger(__name__)

RING_TTL = 30  # secondes
APP_NAME = "Diverse-Cité"


class DiscussChannelMember(models.Model):
    _inherit = 'discuss.channel.member'

    def _rtc_invite_members(self, member_ids=None):
        self.ensure_one()
        candidates = self.env['discuss.channel.member'].search(self._get_rtc_invite_members_domain(member_ids))
        res = super()._rtc_invite_members(member_ids=member_ids)
        invited = candidates.filtered('rtc_inviting_session_id')
        if invited:
            self.channel_id._mobile_call_push('ring', invited, invited[0].rtc_inviting_session_id)
        return res


class DiscussChannel(models.Model):
    _inherit = 'discuss.channel'

    def _rtc_cancel_invitations(self, member_ids=None):
        self.ensure_one()
        domain = [('channel_id', '=', self.id), ('rtc_inviting_session_id', '!=', False)]
        if member_ids:
            domain.append(('id', 'in', member_ids))
        # Avant super : l'invitation (donc la session qui sonnait) est effacée par l'annulation.
        ringing = [(member, member.rtc_inviting_session_id)
                   for member in self.env['discuss.channel.member'].sudo().search(domain)]
        res = super()._rtc_cancel_invitations(member_ids=member_ids)
        # L'iPhone qui a répondu ou refusé sait déjà que l'appel ne sonne plus.
        actor = self.env.context.get('mobile_call_actor_uid')
        by_session = {}
        for member, session in ringing:
            if actor and actor in member.partner_id.user_ids.ids:
                continue
            by_session.setdefault(session, self.env['discuss.channel.member'])
            by_session[session] |= member
        for session, members in by_session.items():
            self._mobile_call_push('end', members, session)
        return res

    @api.model
    def _mobile_call_uuid(self, session_id):
        """Identifiant d'appel stable, le même dans « ring » et « end » (CallKit le rapproche)."""
        return str(uuid.uuid5(uuid.NAMESPACE_URL, f'diverse-call:{self.env.cr.dbname}:{session_id}'))

    def _mobile_call_push(self, event, members, session):
        """Notification VoIP ``ring`` ou ``end`` vers les iPhone des membres donnés."""
        self.ensure_one()
        Queue = self.env['social_mobile.push_queue'].sudo()
        config = Queue._config()
        if not config:
            return
        now = fields.Datetime.now()
        if event == 'ring':
            # Conversation en sourdine : pas de sonnerie (comme pour les messages).
            members = members.filtered(lambda m: not (m.mute_until_dt and m.mute_until_dt > now))
        users = members.partner_id.user_ids.filtered(
            lambda u: u.active and u.has_group('social_base.group_social_user'))
        devices = self.env['social_mobile.device'].sudo().search([('user_id', 'in', users.ids), ('kind', '=', 'voip')])
        if not devices:
            return
        payload = {
            'aps': {},
            'type': 'call',
            'event': event,
            'call_id': self._mobile_call_uuid(session.id),
            'chat_id': self.id,
        }
        if event == 'ring':
            payload['caller'] = self._mobile_call_caller_name(session, config)
        self._mobile_call_push_schedule(devices.ids, payload, config)

    def _mobile_call_caller_name(self, session, config):
        """Discret par défaut, comme les notifications : le nom n'apparaît qu'avec « Nommer
        l'expéditeur »."""
        caller = session.partner_id.user_ids[:1]
        if not config.get('show_sender') or not caller:
            return APP_NAME
        return self.env['club_social_profile.profile'].sudo()._display_name_for_user(caller) or APP_NAME

    def _mobile_call_push_schedule(self, device_ids, payload, config):
        """Envoie après la validation, dans une transaction à part (appareils corrigés ou retirés
        selon la réponse d'Apple). Remplacé dans les tests pour envoyer aussitôt."""
        registry = self.env.registry

        def send():
            try:
                with registry.cursor() as cr:
                    env = api.Environment(cr, SUPERUSER_ID, {})
                    env['social_mobile.push_queue']._mobile_call_send(device_ids, payload, config)
            except Exception:  # noqa: BLE001 - une sonnerie ratée ne doit rien casser d'autre
                _logger.warning("Sonnerie d'appel non envoyée", exc_info=True)

        self.env.cr.postcommit.add(send)


class SocialMobilePushQueue(models.Model):
    _inherit = 'social_mobile.push_queue'

    @api.model
    def _mobile_call_send(self, device_ids, payload, config):
        devices = self.env['social_mobile.device'].sudo().browse(device_ids).exists()
        if not devices:
            return
        expiration = time.time() + RING_TTL
        with self._http_client() as client:
            for device in devices:
                outcome = self._deliver(client, device, config, payload, None, push_type='voip', expiration=expiration)
                if outcome == 'stop':
                    return
