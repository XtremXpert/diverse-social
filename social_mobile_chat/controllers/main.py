"""Messagerie dans l'API mobile (/api/social/v1/chats). Contrat : README.md du module."""
import base64
import binascii

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

    @http.route(f'{API}/chats/<int:channel_id>/voice', methods=['POST'], **ROUTE)
    def post_voice(self, channel_id):
        """Message vocal : ``{"data": "<m4a en base64>"}``."""
        channel = self._channel(channel_id)
        if not channel:
            return error(404, 'not_found', "Conversation introuvable.")
        body = json_body()
        if body is None or not isinstance(body.get('data'), str):
            return error(400, 'invalid_json', "Corps JSON attendu : {\"data\": base64}.")
        try:
            data = base64.b64decode(body['data'], validate=True)
        except (binascii.Error, ValueError):
            return error(400, 'invalid', "Audio illisible (base64 attendu).")
        return self._run(lambda: json_response({'message': channel._mobile_post_voice(request.env.user, data)}))

    @http.route(f'{API}/chats/<int:channel_id>/attachments', methods=['POST'], **ROUTE)
    def post_attachment(self, channel_id):
        """Photo ou fichier : ``{"data": base64, "name": "photo.jpg", "body"?: légende}``."""
        channel = self._channel(channel_id)
        if not channel:
            return error(404, 'not_found', "Conversation introuvable.")
        body = json_body()
        if body is None or not isinstance(body.get('data'), str):
            return error(400, 'invalid_json', "Corps JSON attendu : {\"data\": base64, \"name\"}.")
        try:
            data = base64.b64decode(body['data'], validate=True)
        except (binascii.Error, ValueError):
            return error(400, 'invalid', "Fichier illisible (base64 attendu).")
        name = body.get('name') if isinstance(body.get('name'), str) else ''
        caption = body.get('body') if isinstance(body.get('body'), str) else None
        return self._run(lambda: json_response({'message': channel._mobile_post_file(request.env.user, name, data, caption)}))

    @http.route(f'{API}/chats/<int:channel_id>/attachments/<int:attachment_id>', methods=['GET'], **ROUTE)
    def attachment(self, channel_id, attachment_id, thumb=None):
        """Contenu d'une pièce jointe de la conversation ; ``?thumb=1`` : miniature d'une image."""
        channel = self._channel(channel_id)
        if not channel:
            return error(404, 'not_found', "Conversation introuvable.")

        def run():
            data, mimetype = channel._mobile_attachment(request.env.user, attachment_id, thumb=thumb in ('1', 'true'))
            return request.make_response(data, headers=[
                ('Content-Type', mimetype), ('Content-Length', str(len(data))),
                ('Cache-Control', 'private, max-age=86400'), ('X-Content-Type-Options', 'nosniff')])
        return self._run(run)

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
