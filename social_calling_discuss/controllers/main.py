from odoo import http
from odoo.http import request
from odoo.exceptions import AccessDenied


class DiscussCalling(http.Controller):
    """Lance un appel via Discuss natif (WebRTC).

    Crée/récupère le DM Discuss entre les deux membres et redirige vers la vue
    de canal Discuss publique (/discuss/channel/<id>), où l'appel vidéo se
    lance nativement. Le média passe en direct entre les navigateurs, ou par
    le SFU d'Odoo quand il est configuré."""

    @http.route(['/discuss-call/<int:user_id>'], type='http', auth='user', website=True)
    def discuss_call_start(self, user_id, **kw):
        user = request.env.user
        callee = request.env['res.users'].sudo().browse(user_id)
        if not callee.exists() or callee.id == user.id or not callee.partner_id:
            return request.redirect('/my/messages')

        # Blocage mutuel.
        Block = request.env['social_safety.block'].sudo()
        if Block.search([
            '|', '&', ('blocker_id', '=', user.id), ('blocked_id', '=', callee.id),
                 '&', ('blocker_id', '=', callee.id), ('blocked_id', '=', user.id),
        ], limit=1):
            raise AccessDenied()

        # sudo : la création de discuss.channel est réservée aux utilisateurs
        # internes (base.group_user). Nos membres sont des utilisateurs portail.
        # .sudo() bypass l'ACL de création SANS changer self.env.user (qui reste
        # l'utilisateur portail) → _get_or_create_chat ajoute bien son partenaire
        # comme membre, donc l'ir.rule laissera ensuite ouvrir /discuss/channel/<id>.
        channel = request.env['discuss.channel'].sudo()._get_or_create_chat([callee.partner_id.id])

        # Sonnerie chez l'appelé : service incoming_call.js de social_calling,
        # chargé globalement sur le portail. La
        # page Discuss publique n'embarque pas le client Discuss complet qui
        # écouterait les invitations RTC → sans ça, l'appelé ne saurait jamais
        # qu'on l'appelle. provider='discuss' : « Répondre » ouvre le canal,
        # « Refuser » refuse l'invitation Discuss du canal (channel_id).
        request.env['bus.bus']._sendone(
            callee.partner_id,
            'social_calling/incoming_call',
            {
                'session_id': 'discuss-%s' % channel.id,
                'caller_name': request.env['club_social_profile.profile']._display_name_for_user(user),
                'call_type': 'video',
                'room_url': '/discuss/channel/%s' % channel.id,
                'provider': 'discuss',
                'channel_id': channel.id,
            },
        )
        return request.redirect('/discuss/channel/%s' % channel.id)
