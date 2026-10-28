from odoo import http
from odoo.exceptions import ValidationError
from odoo.http import request

from odoo.addons.social_mobile.controllers.main import (
    API, ROUTE, error, json_body, json_response)


class SocialEssenceApi(http.Controller):
    """Questionnaires du membre : questions du catalogue, ses réponses, sa note de limites."""

    def _member_or_error(self):
        if not request.env.user.has_group('social_base.group_social_user'):
            return error(403, 'not_member', "Réservé aux membres.")
        return None

    @http.route(f'{API}/essence/questions', methods=['GET'], **ROUTE)
    def questions(self):
        """Catalogue questions, optionally filtered by ``?section=``."""
        if err := self._member_or_error():
            return err
        domain = [('active', '=', True)]
        if section := request.params.get('section'):
            domain.append(('section', '=', section))
        questions = request.env['social_essence.question'].sudo().search(domain)
        return json_response({'questions': [
            {'id': q.id, 'name': q.name, 'section': q.section, 'allow_detail': q.allow_detail}
            for q in questions]})

    @http.route(f'{API}/essence/answers', methods=['GET'], **ROUTE)
    def answers_get(self):
        if err := self._member_or_error():
            return err
        sheet = request.env['social_essence.sheet'].sudo().search(
            [('user_id', '=', request.env.uid)], limit=1)
        return json_response(sheet._as_dict() if sheet else {'hard_limit_text': '',
                                                             'needs_hard_limit': False,
                                                             'answers': []})

    @http.route(f'{API}/essence/answers', methods=['POST'], **ROUTE)
    def answers_set(self):
        """Upsert one answer: ``{"question_id": N, "value": "only|open|never", "detail": "…"}``."""
        if err := self._member_or_error():
            return err
        body = json_body()
        if body is None or not body.get('question_id'):
            return error(400, 'invalid', 'Corps attendu : {"question_id", "value", "detail"}.')
        try:
            sheet = request.env['social_essence.answer']._api_set(
                body['question_id'], body.get('value'), body.get('detail', ''))
        except ValidationError as e:
            return error(400, 'invalid', str(e))
        return json_response(sheet._as_dict())

    @http.route(f'{API}/essence/sheet', methods=['POST'], **ROUTE)
    def sheet_set(self):
        """Set the member's hard-limit note: ``{"hard_limit_text": "…"}`` (required once a
        'never' answer exists, 300 chars)."""
        if err := self._member_or_error():
            return err
        body = json_body() or {}
        text = str(body.get('hard_limit_text') or '')[:300]
        sheet = request.env['social_essence.sheet'].sudo()._mine()
        sheet.hard_limit_text = text
        return json_response(sheet._as_dict())
