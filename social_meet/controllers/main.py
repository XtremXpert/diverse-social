"""API mobile des rencontres (/api/social/v1/meets).

Contrat : docs/spec-rencontres.md (dépôt diverse-odoo).
"""
from odoo import http
from odoo.exceptions import ValidationError
from odoo.http import request

from odoo.addons.social_mobile.controllers.main import (
    API,
    ROUTE,
    error,
    iso,
    json_body,
    json_response,
)


class SocialMeetApi(http.Controller):

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _member_or_error(self):
        if not request.env.user.has_group('social_base.group_social_user'):
            return error(403, 'not_member', "Réservé aux membres.")
        return None

    def _visible_meet(self, meet_id):
        """Rencontre que l'utilisateur courant peut voir, ou None (404)."""
        meet = request.env['social_meet.meet'].sudo().browse(int(meet_id))
        if not meet.exists():
            return None
        user = request.env.user
        if meet.host_user_id == user or meet._check_social_access(user):
            return meet
        return None

    def _payload(self, meet):
        data = meet._as_dict(request.env.user)
        data['date_start'] = iso(data['date_start'])
        data['date_end'] = iso(data['date_end'])
        return data

    # ── Routes ───────────────────────────────────────────────────────────────

    @http.route(f'{API}/meets', methods=['GET'], **ROUTE)
    def meets_list(self, **_kw):
        """Rencontres visibles : spontanées en cours et planifiées à venir."""
        if err := self._member_or_error():
            return err
        meets = request.env['social_meet.meet']._api_list(request.env.user)
        return json_response({'meets': [self._payload(m) for m in meets]})

    @http.route(f'{API}/meets', methods=['POST'], **ROUTE)
    def meets_create(self):
        """Créer une rencontre.

        Corps : ``{"kind": "now"|"planned", "hours": 1–12, "start": "<ISO>",
        "latitude"?, "longitude"?, "safe_zone_id"?, "relation_id"?,
        "audience"?, "seats_max"?}``.
        """
        if err := self._member_or_error():
            return err
        body = json_body()
        if body is None:
            return error(400, 'invalid_json', "Corps JSON attendu.")
        kind = body.get('kind', 'now')
        if kind not in ('now', 'planned'):
            return error(400, 'invalid', "Type de rencontre inconnu.")
        if kind == 'planned' and not body.get('start'):
            return error(400, 'invalid',
                         'Corps attendu : {"kind": "planned", "start": "<ISO>"}.')
        try:
            meet = request.env['social_meet.meet']._api_create(
                body.get('start'),
                hours=body.get('hours', 3),
                kind=kind,
                latitude=body.get('latitude'),
                longitude=body.get('longitude'),
                safe_zone_id=body.get('safe_zone_id'),
                relation_id=body.get('relation_id'),
                audience=body.get('audience'),
                seats_max=body.get('seats_max', 0),
            )
        except ValidationError as exc:
            return error(400, 'invalid', str(exc))
        return json_response(self._payload(meet), status=201)

    @http.route(f'{API}/meets/<int:meet_id>', methods=['GET'], **ROUTE)
    def meets_detail(self, meet_id, **_kw):
        if err := self._member_or_error():
            return err
        meet = self._visible_meet(meet_id)
        if meet is None:
            return error(404, 'not_found', "Rencontre introuvable.")
        return json_response(self._payload(meet))

    @http.route(f'{API}/meets/<int:meet_id>/join', methods=['POST'], **ROUTE)
    def meets_join(self, meet_id, **_kw):
        if err := self._member_or_error():
            return err
        meet = self._visible_meet(meet_id)
        if meet is None:
            return error(404, 'not_found', "Rencontre introuvable.")
        try:
            meet._api_join(request.env.user)
        except ValidationError as exc:
            return error(403, 'forbidden', str(exc))
        return json_response(self._payload(meet))

    @http.route(f'{API}/meets/<int:meet_id>/leave', methods=['POST'], **ROUTE)
    def meets_leave(self, meet_id, **_kw):
        if err := self._member_or_error():
            return err
        meet = self._visible_meet(meet_id)
        if meet is None:
            return error(404, 'not_found', "Rencontre introuvable.")
        try:
            meet._api_leave(request.env.user)
        except ValidationError as exc:
            return error(403, 'forbidden', str(exc))
        return json_response(self._payload(meet))

    @http.route(f'{API}/meets/<int:meet_id>/cancel', methods=['POST'], **ROUTE)
    def meets_cancel(self, meet_id, **_kw):
        if err := self._member_or_error():
            return err
        meet = self._visible_meet(meet_id)
        if meet is None:
            return error(404, 'not_found', "Rencontre introuvable.")
        if meet.host_user_id != request.env.user:
            return error(403, 'forbidden', "Seul l'hôte annule la rencontre.")
        meet.action_cancel()
        return json_response(self._payload(meet))

    @http.route(f'{API}/meets/<int:meet_id>/publish', methods=['POST'], **ROUTE)
    def meets_publish(self, meet_id, **_kw):
        """Créer l'événement Odoo qui porte une rencontre planifiée (brouillon)."""
        if err := self._member_or_error():
            return err
        meet = self._visible_meet(meet_id)
        if meet is None:
            return error(404, 'not_found', "Rencontre introuvable.")
        if meet.host_user_id != request.env.user:
            return error(403, 'forbidden', "Seul l'hôte publie la rencontre.")
        try:
            meet._api_publish()
        except ValidationError as exc:
            return error(400, 'invalid', str(exc))
        return json_response(self._payload(meet))
