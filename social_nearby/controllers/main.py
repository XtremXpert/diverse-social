"""Grille de proximité dans l'API mobile (/api/social/v1). Contrat : README.md du module."""
import base64

from odoo import fields, http
from odoo.exceptions import ValidationError
from odoo.http import request

from odoo.addons.social_nearby.models.position import DEFAULT_MEET_HOURS
from odoo.addons.social_mobile.controllers.main import API, ROUTE, error, iso, json_body, json_response


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
        return json_response(dict(grid, meet_until=iso(grid['meet_until'])))

    @http.route(f'{API}/meet', methods=['POST'], **ROUTE)
    def meet(self):
        """Mode « Je veux rencontrer » : ``{"active": true, "hours": 3}`` (1 à 12 heures, 3 par
        défaut), ``"start"`` (ISO) pour une date et heure de début planifiées au lieu de maintenant,
        ``"latitude"`` et ``"longitude"`` pour un lieu de rencontre choisi ailleurs ;
        ``{"active": false}`` pour l'arrêter."""
        if err := self._member_or_error():
            return err
        body = json_body()
        if body is None or not isinstance(body.get('active'), bool):
            return error(400, 'invalid', "Corps attendu : {\"active\": true|false, \"hours\": 1–12}.")
        try:
            start_at = None
            if body.get('start'):
                try:
                    start_at = fields.Datetime.from_string(body['start'])
                except ValueError:
                    return error(400, 'invalid', "Date de début invalide (format ISO attendu).")
            until = request.env['social_nearby.position']._api_meet(
                body['active'], body.get('hours', DEFAULT_MEET_HOURS), body.get('latitude'),
                body.get('longitude'), start_at=start_at)
        except ValidationError as e:
            return error(400, 'invalid', str(e))
        if until is None:
            return error(409, 'no_position', "Partagez votre position pour activer ce mode.")
        position = request.env['social_nearby.position'].sudo().search(
            [('user_id', '=', request.env.uid)], limit=1)
        spot = position._meet_spot() if until else None
        return json_response({'meet_until': iso(until) if until else None, 'meet_spot': spot,
                              'meet_start_at': iso(position.meet_start_at) if position.meet_start_at else None})

    @http.route(f'{API}/meets', methods=['GET'], **ROUTE)
    def meets_list(self):
        """Rencontres proposées visibles pour le membre (les siennes et celles de son audience)."""
        if err := self._member_or_error():
            return err
        meets = request.env['social_nearby.meet']._api_list()
        return json_response({'meets': [dict(m, start_at=iso(m['start_at']), until=iso(m['until']))
                                      for m in meets]})

    @http.route(f'{API}/safe_zones', methods=['GET'], **ROUTE)
    def safe_zones(self):
        """Safe Zones actives (lieux physiques de rencontre nommés)."""
        if err := self._member_or_error():
            return err
        return json_response({'safe_zones': request.env['social_nearby.safe_zone']._api_list()})

    @http.route(f'{API}/meets', methods=['POST'], **ROUTE)
    def meets_create(self):
        """Proposer une rencontre : ``{"start": "<ISO>", "hours": 3, "latitude":…, "longitude":…,
        "audience": "connections"|"nearby"}``."""
        if err := self._member_or_error():
            return err
        body = json_body()
        if body is None or not body.get('start'):
            return error(400, 'invalid', 'Corps attendu : {"start": "<ISO>"}.')
        try:
            start_at = fields.Datetime.from_string(body['start'])
        except ValueError:
            return error(400, 'invalid', 'Date de début invalide (format ISO attendu).')
        try:
            meet = request.env['social_nearby.meet']._api_create(
                start_at, body.get('hours', DEFAULT_MEET_HOURS), body.get('latitude'),
                body.get('longitude'), body.get('audience', 'connections'),
                safe_zone_id=body.get('safe_zone_id'), relation_id=body.get('relation_id'))
        except ValidationError as e:
            return error(400, 'invalid', str(e))
        if meet is None:
            return error(409, 'no_position', 'Partagez votre position pour proposer une rencontre.')
        return json_response(meet._as_dict() | {'start_at': iso(meet.start_at), 'until': iso(meet.until)})

    @http.route(f'{API}/meets/<int:meet_id>/reply', methods=['POST'], **ROUTE)
    def meets_reply(self, meet_id):
        """Demander à rejoindre une rencontre proposée (en attente d'approbation)."""
        if err := self._member_or_error():
            return err
        meet = request.env['social_nearby.meet'].sudo().browse(meet_id)
        try:
            reply = request.env['social_nearby.meet.reply']._api_reply(meet)
        except ValidationError as e:
            return error(404, 'not_found', str(e))
        return json_response({'state': reply.state})

    @http.route(f'{API}/meets/<int:meet_id>/cancel', methods=['POST'], **ROUTE)
    def meets_cancel(self, meet_id):
        """Annuler sa propre rencontre proposée."""
        if err := self._member_or_error():
            return err
        meet = request.env['social_nearby.meet'].sudo().browse(meet_id)
        try:
            meet._api_cancel()
        except ValidationError as e:
            return error(403, 'forbidden', str(e))
        return json_response({'state': meet.state})

    @http.route(f'{API}/meets/replies/<int:reply_id>', methods=['POST'], **ROUTE)
    def meets_answer(self, reply_id):
        """Le proposant accepte (``{"accept": true}``) ou refuse une réponse ; accepter confirme
        la rencontre."""
        if err := self._member_or_error():
            return err
        body = json_body() or {}
        reply = request.env['social_nearby.meet.reply'].sudo().browse(reply_id)
        try:
            reply._api_answer(bool(body.get('accept')))
        except ValidationError as e:
            return error(403, 'forbidden', str(e))
        return json_response({'state': reply.state, 'meet_state': reply.meet_id.state})

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
        # Odoo 20 : un champ image est un BinaryValue (octets bruts), plus du base64.
        image = profile.profile_image
        return request.make_response(image.content, headers=[
            ('Content-Type', image.mimetype or 'image/png'), ('Cache-Control', 'private, max-age=300')])
