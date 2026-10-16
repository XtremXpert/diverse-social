"""Appels dans l'API mobile (/api/social/v1/chats/<id>/call). Contrat : README.md du module."""
from odoo import http
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.http import request

from odoo.addons.social_mobile.controllers.main import API, ROUTE, error, json_body, json_response

from ..models.discuss_channel import CallEnded, CallUnavailable


class SocialMobileCallApi(http.Controller):

    def _run(self, channel_id, fn):
        channel = request.env['discuss.channel'].sudo().browse(channel_id).exists()
        if not channel:
            return error(404, 'not_found', "Conversation introuvable.")
        try:
            return json_response(fn(channel, request.env.user))
        except AccessError:
            return error(404, 'not_found', "Conversation introuvable.")
        except CallEnded as e:
            return error(410, 'call_ended', str(e))
        except CallUnavailable as e:
            return error(503, 'call_unavailable', str(e))
        except (UserError, ValidationError) as e:
            return error(403, 'refused', str(e))

    def _session_id(self):
        body = json_body() or {}
        try:
            return int(body.get('session_id') or 0), body
        except (TypeError, ValueError):
            return 0, body

    @http.route(f'{API}/chats/<int:channel_id>/call', methods=['GET'], **ROUTE)
    def call_state(self, channel_id):
        return self._run(channel_id, lambda c, u: {'call': c._mobile_call_state(u)})

    @http.route(f'{API}/chats/<int:channel_id>/call/join', methods=['POST'], **ROUTE)
    def call_join(self, channel_id):
        return self._run(channel_id, lambda c, u: c._mobile_call_join(u))

    @http.route(f'{API}/chats/<int:channel_id>/call/ping', methods=['POST'], **ROUTE)
    def call_ping(self, channel_id):
        session_id, _body = self._session_id()
        return self._run(channel_id, lambda c, u: {'call': c._mobile_call_ping(u, session_id)})

    @http.route(f'{API}/chats/<int:channel_id>/call/mute', methods=['POST'], **ROUTE)
    def call_mute(self, channel_id):
        session_id, body = self._session_id()
        return self._run(channel_id, lambda c, u: {'call': c._mobile_call_mute(u, session_id, body.get('muted'))})

    @http.route(f'{API}/chats/<int:channel_id>/call/leave', methods=['POST'], **ROUTE)
    def call_leave(self, channel_id):
        session_id, _body = self._session_id()
        return self._run(channel_id, lambda c, u: {'call': c._mobile_call_leave(u, session_id)})

    @http.route(f'{API}/chats/<int:channel_id>/call/decline', methods=['POST'], **ROUTE)
    def call_decline(self, channel_id):
        return self._run(channel_id, lambda c, u: {'call': c._mobile_call_decline(u)})
