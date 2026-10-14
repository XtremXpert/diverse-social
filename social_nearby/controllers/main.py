"""Grille de proximité dans l'API mobile (/api/social/v1). Contrat : README.md du module."""
import base64

from odoo import http
from odoo.exceptions import ValidationError
from odoo.http import request

from odoo.addons.social_mobile.controllers.main import API, ROUTE, error, json_body, json_response


class SocialNearbyApi(http.Controller):

    def _member_or_error(self):
        if not request.env.user.has_group('social_base.group_social_user'):
            return error(403, 'not_member', "Réservé aux membres.")
        return None

    @http.route(f'{API}/position', methods=['POST'], **ROUTE)
    def report_position(self):
        """Position de l'appareil ; Odoo n'en garde que la case (≈ 550 m)."""
        if err := self._member_or_error():
            return err
        body = json_body()
        if body is None:
            return error(400, 'invalid_json', "Corps JSON attendu.")
        try:
            request.env['social_nearby.position']._api_report(body.get('latitude'), body.get('longitude'))
        except ValidationError as e:
            return error(400, 'invalid', str(e))
        return json_response({'shared': True})

    @http.route(f'{API}/position', methods=['DELETE'], **ROUTE)
    def forget_position(self):
        request.env['social_nearby.position']._api_forget()
        return json_response({'shared': False})

    @http.route(f'{API}/nearby', methods=['GET'], **ROUTE)
    def nearby(self, radius_km=None, **_kw):
        if err := self._member_or_error():
            return err
        try:
            radius = float(radius_km) if radius_km else None
        except ValueError:
            return error(400, 'invalid', "Rayon invalide.")
        grid = request.env['social_nearby.position']._api_grid(request.env.user, radius_km=radius)
        if grid is None:
            return error(409, 'no_position', "Partagez votre position pour voir la grille.")
        return json_response(grid)

    @http.route(f'{API}/users/<int:user_id>/photo', methods=['GET'], **ROUTE)
    def user_photo(self, user_id):
        """Photo de profil, seulement si le profil montre ses informations détaillées au demandeur."""
        if err := self._member_or_error():
            return err
        viewer = request.env.user
        profile = request.env['club_social_profile.profile'].sudo().search([('user_id', '=', user_id)], limit=1)
        if (not profile or not profile.profile_image or profile.is_banned
                or request.env['social_safety.block'].is_blocked(viewer, profile.user_id)
                or not profile.can_see_detailed_info(viewer)):
            return error(404, 'not_found', "Photo introuvable.")
        return request.make_response(base64.b64decode(profile.profile_image), headers=[
            ('Content-Type', 'image/png'), ('Cache-Control', 'private, max-age=300')])
