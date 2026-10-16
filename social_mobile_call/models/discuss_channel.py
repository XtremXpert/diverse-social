from odoo import _, models
from odoo.exceptions import UserError

from odoo.addons.mail.tools import discuss


class CallUnavailable(UserError):
    """Le serveur d'appel (SFU) n'est pas configuré ou ne répond pas."""


class CallEnded(UserError):
    """La session d'appel n'existe plus (raccrochée, expirée, ou rejointe ailleurs)."""


class DiscussChannel(models.Model):
    """Appels audio de l'application mobile.

    L'application rejoint l'appel Discuss de la conversation comme le ferait le site, mais
    toujours par le SFU d'Odoo : elle reçoit l'adresse du SFU et un jeton signé par Odoo, puis
    échange l'audio directement avec le SFU. Les sessions d'appel restent celles de Discuss
    (``discuss.channel.rtc.session``), donc le site voit et entend les participants mobiles."""
    _inherit = 'discuss.channel'

    def _mobile_payload(self, user):
        payload = super()._mobile_payload(user)
        payload['call'] = self.sudo()._mobile_call_summary(user)
        return payload

    def _mobile_call_member(self, user):
        channel = self._mobile_check_member(user)
        return channel, channel.channel_member_ids.filtered(lambda m: m.partner_id == user.partner_id)[:1]

    def _mobile_call_summary(self, user):
        """État court pour la liste des conversations : appel en cours, et s'il sonne pour ``user``."""
        sessions = self.rtc_session_ids
        member = self.channel_member_ids.filtered(lambda m: m.partner_id == user.partner_id)[:1]
        return {
            'active': bool(sessions),
            'participant_count': len(sessions),
            'ringing': bool(member.rtc_inviting_session_id),
        }

    def _mobile_call_state(self, user):
        channel, member = self._mobile_call_member(user)
        Profile = self.env['club_social_profile.profile'].sudo()
        participants = []
        for session in channel.rtc_session_ids:
            other = session.partner_id.user_ids[:1]
            participants.append({
                'session_id': session.id,
                'name': Profile._display_name_for_user(other) if other else (session.partner_id.name or ''),
                'is_self': session.channel_member_id == member,
                'is_muted': session.is_muted,
            })
        return dict(channel._mobile_call_summary(user), participants=participants)

    def _mobile_call_session(self, user, session_id):
        channel, member = self._mobile_call_member(user)
        session = channel.rtc_session_ids.filtered(
            lambda s: s.id == int(session_id or 0) and s.channel_member_id == member)
        if not session:
            raise CallEnded(_("L'appel est terminé."))
        return channel, member, session

    def _mobile_call_join(self, user):
        """Rejoint (ou lance) l'appel de la conversation par le SFU. Sonne chez les autres membres
        quand l'appel commence, comme Discuss."""
        channel, member = self._mobile_call_member(user)
        if channel.is_readonly:
            raise UserError(_("Impossible d'appeler dans cette conversation."))
        # Même règle que pour écrire : pas d'appel entre deux personnes dont l'une a bloqué l'autre.
        channel.with_user(user)._smd_assert_not_blocked_on_post()
        if not discuss.get_sfu_url(self.env):
            raise CallUnavailable(_("Les appels ne sont pas disponibles pour le moment."))
        # with_user : la session est créée par le membre (create_uid identifie son jeton SFU).
        member_user = member.with_user(user).sudo()
        member_user._rtc_join_call()
        session = member_user.rtc_session_ids[:1]
        ice_servers = self.env['mail.ice.server'].sudo()._get_ice_servers()
        member_user._join_sfu(ice_servers, force=True)
        server = member_user._get_rtc_server_info(session, ice_servers)
        if not server:
            # SFU injoignable : on ne laisse pas sonner un appel que l'application ne peut pas tenir.
            member_user._rtc_leave_call(session.id)
            raise CallUnavailable(_("Le serveur d'appel ne répond pas. Réessayez dans un instant."))
        return {
            'session_id': session.id,
            'server': {
                'url': server['url'],
                'channel_uuid': server['channelUUID'],
                'token': server['jsonWebToken'],
            },
            'ice_servers': ice_servers or [],
            'call': channel._mobile_call_state(user),
        }

    def _mobile_call_ping(self, user, session_id):
        """Garde la session en vie (Odoo efface celles restées 75 s sans nouvelles)."""
        channel, _member, session = self._mobile_call_session(user, session_id)
        session.write({})  # met à jour write_date, comme /discuss/channel/ping
        return channel._mobile_call_state(user)

    def _mobile_call_mute(self, user, session_id, muted):
        channel, _member, session = self._mobile_call_session(user, session_id)
        session._update_and_broadcast({'is_muted': bool(muted)})
        return channel._mobile_call_state(user)

    def _mobile_call_leave(self, user, session_id):
        channel, member = self._mobile_call_member(user)
        member.with_user(user).sudo()._rtc_leave_call(int(session_id or 0) or None)
        return channel._mobile_call_state(user)

    def _mobile_call_decline(self, user):
        channel, member = self._mobile_call_member(user)
        channel._rtc_cancel_invitations(member_ids=member.ids)
        return channel._mobile_call_state(user)
