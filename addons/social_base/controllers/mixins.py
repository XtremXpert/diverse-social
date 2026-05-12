import json

from odoo.http import request
from odoo.exceptions import AccessError


class SocialBaseMixin:
    """Utilitaires partagés pour les contrôleurs social_base."""

    def _validate_auth(self):
        if not request.env.user or request.env.user.id == request.env.ref('base.public_user').id:
            raise AccessError('Authentication required')
        return request.env.user

    def _json_response(self, data, status=200):
        return request.make_json_response(data, status=status)

    def _success_response(self, data):
        return self._json_response({'success': True, 'data': data})

    def _error_response(self, message, code='ERROR', status=400):
        return self._json_response({'success': False, 'error': message, 'code': code}, status=status)

    def _get_json_body(self):
        try:
            data = request.httprequest.get_data(as_text=True)
            return json.loads(data) if data else {}
        except (ValueError, TypeError):
            return {}
