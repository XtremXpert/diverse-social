"""Messagerie dans l'API mobile (/api/social/v1/chats). Contrat : README.md du module."""
from odoo import http
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.http import request

from odoo.addons.social_mobile.controllers.main import API, ROUTE, error, json_body, json_response


class SocialMobileChatApi(http.Controller):

    def _member_or_error(self):
        if not request.env.user.has_group('social_base.group_social_user'):
            return error(403, 'not_member', "Réservé aux membres.")
        return None

    def _channel(self, channel_id):
        return request.env['discuss.channel'].sudo().browse(channel_id).exists()

    def _run(self, fn):
        try:
            return fn()
        except AccessError:
            return error(404, 'not_found', "Conversation introuvable.")
        except (UserError, ValidationError) as e:
            return error(403, 'refused', str(e))

    @http.route(f'{API}/chats', methods=['GET'], **ROUTE)
    def list_chats(self):
        if err := self._member_or_error():
            return err
        user = request.env.user
        channels = request.env['discuss.channel']._mobile_channels(user)
        return json_response({'chats': [c._mobile_payload(user) for c in channels]})

    @http.route(f'{API}/chats', methods=['POST'], **ROUTE)
    def open_chat(self):
        """Ouvre (ou retrouve) la conversation à deux avec un membre : ``{"user_id"}``."""
        if err := self._member_or_error():
            return err
        body = json_body() or {}
        user = request.env.user
        other = request.env['res.users'].sudo().browse(int(body.get('user_id') or 0)).exists()
        return self._run(lambda: json_response({
            'chat': request.env['discuss.channel']._mobile_open_chat(user, other)._mobile_payload(user)}))

    @http.route(f'{API}/chats/<int:channel_id>', methods=['GET'], **ROUTE)
    def get_chat(self, channel_id):
        channel = self._channel(channel_id)
        if not channel:
            return error(404, 'not_found', "Conversation introuvable.")
        return self._run(lambda: json_response({'chat': channel._mobile_payload(request.env.user)}))

    @http.route(f'{API}/chats/<int:channel_id>/messages', methods=['GET'], **ROUTE)
    def messages(self, channel_id, before=None, after=None, limit=None, **_kw):
        channel = self._channel(channel_id)
        if not channel:
            return error(404, 'not_found', "Conversation introuvable.")
        try:
            before = int(before) if before else None
            after = int(after) if after else None
            limit = int(limit) if limit else None
        except ValueError:
            return error(400, 'invalid', "Paramètre invalide.")
        return self._run(lambda: json_response({
            'messages': channel._mobile_messages(request.env.user, before=before, after=after, limit=limit)}))

    @http.route(f'{API}/chats/<int:channel_id>/messages', methods=['POST'], **ROUTE)
    def post_message(self, channel_id):
        channel = self._channel(channel_id)
        if not channel:
            return error(404, 'not_found', "Conversation introuvable.")
        body = json_body()
        if body is None:
            return error(400, 'invalid_json', "Corps JSON attendu.")
        return self._run(lambda: json_response({'message': channel._mobile_post(request.env.user, body.get('body'))}))

    @http.route(f'{API}/chats/<int:channel_id>/read', methods=['POST'], **ROUTE)
    def mark_read(self, channel_id):
        channel = self._channel(channel_id)
        if not channel:
            return error(404, 'not_found', "Conversation introuvable.")
        body = json_body() or {}

        def run():
            channel._mobile_mark_read(request.env.user, body.get('last_message_id'))
            return json_response({'read': True})
        return self._run(run)

    @http.route(f'{API}/chats/unread', methods=['GET'], **ROUTE)
    def unread(self):
        """Total des non-lus (pastille de l'onglet), sans charger les conversations."""
        if err := self._member_or_error():
            return err
        user = request.env.user
        channels = request.env['discuss.channel']._mobile_channels(user)
        members = channels.channel_member_ids.filtered(lambda m: m.partner_id == user.partner_id)
        return json_response({'unread': sum(members.mapped('message_unread_counter'))})
