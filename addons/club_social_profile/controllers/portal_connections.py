"""Form-based connection request — used by the "+ Connect" button on /profile/<id>.

The button POSTs to /api/connections/request/<target_user_id> with a CSRF token,
expecting a redirect back to the profile. The JSON API at /social/api/connections
is the right surface for AJAX clients, but the public profile template uses a
plain HTML form, so we expose this form-level wrapper here.
"""
import logging

from werkzeug.urls import url_encode

from odoo import http
from odoo.exceptions import AccessError, ValidationError
from odoo.http import request

_logger = logging.getLogger(__name__)


class PortalConnectionRequest(http.Controller):

    @http.route(
        '/api/connections/request/<int:target_user_id>',
        type='http', auth='user', methods=['POST'], website=True, csrf=True,
    )
    def portal_connection_request(self, target_user_id, **kwargs):
        Connection = request.env['club_social_profile.connection'].sudo()
        redirect_base = f'/profile/{target_user_id}'
        try:
            # Savepoint: _check_unique_connection raises after the row is partially
            # inserted; without a savepoint the rollback wouldn't reach it.
            with request.env.cr.savepoint():
                Connection.create({
                    'user_id': request.env.user.id,
                    'connected_user_id': target_user_id,
                    'connection_type': 'friend',
                })
        except ValidationError as e:
            return request.redirect(f'{redirect_base}?{url_encode({"error": str(e)})}')
        except AccessError as e:
            return request.redirect(f'{redirect_base}?{url_encode({"error": str(e)})}')
        except Exception:
            _logger.exception('Error creating connection request to user %s', target_user_id)
            return request.redirect(f'{redirect_base}?error=internal_error')
        return request.redirect(f'{redirect_base}?connection_requested=1')
