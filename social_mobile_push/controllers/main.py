"""Enregistrement des iPhone pour les notifications (/api/social/v1/devices)."""
from odoo import http
from odoo.exceptions import ValidationError
from odoo.http import request

from odoo.addons.social_mobile.controllers.main import API, ROUTE, error, json_body, json_response


class SocialMobilePushApi(http.Controller):

    @http.route(f'{API}/devices', methods=['POST'], **ROUTE)
    def register(self):
        """``{"token", "environment": "production"|"sandbox"}`` : à chaque lancement de l'app."""
        body = json_body()
        if body is None:
            return error(400, 'invalid_json', "Corps JSON attendu.")
        try:
            request.env['social_mobile.device']._api_register(body.get('token'), body.get('environment') or 'production')
        except ValidationError as e:
            return error(400, 'invalid', str(e))
        return json_response({'registered': True})

    @http.route(f'{API}/devices', methods=['DELETE'], **ROUTE)
    def unregister(self):
        """Déconnexion de l'app : ``{"token"}`` (sans jeton, tous mes appareils)."""
        body = json_body() or {}
        request.env['social_mobile.device']._api_unregister(body.get('token'))
        return json_response({'registered': False})
