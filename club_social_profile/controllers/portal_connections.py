"""Form-based connection actions + the /my/connections listing page.

The public profile template renders three buttons depending on the connection
state with the viewing user (cf. portal_profile_public.xml):

  - "+ Connect"          → POST /api/connections/request/<target_user_id>
  - "Accept the request" → POST /api/connections/accept/<target_user_id>
  - "✓ Connected"        → POST /api/connections/remove/<target_user_id> (unfriend)

The JSON API at /social/api/connections is the right surface for AJAX clients,
but those template buttons are plain HTML forms with a CSRF token, so we expose
form-level wrappers here that redirect back to the profile page.

/my/connections is the portal listing referenced from the dashboard, the public
profile sidebar, social_negotiation and social_reputation — it shows the user's
accepted connections plus the pending requests they sent and received.
"""
import logging

from werkzeug.urls import url_encode

from odoo import http
from odoo.exceptions import AccessError, ValidationError
from odoo.http import request

_logger = logging.getLogger(__name__)


class PortalConnectionActions(http.Controller):

    @http.route('/my/connections', type='http', auth='user', website=True, sitemap=False)
    def my_connections(self, **kwargs):
        """Render the current user's connections — accepted, pending sent, pending received."""
        Connection = request.env['club_social_profile.connection'].sudo()
        user = request.env.user
        accepted = Connection.search(
            [('user_id', '=', user.id), ('state', '=', 'accepted')],
            order='create_date desc',
        )
        pending_sent = Connection.search(
            [('user_id', '=', user.id), ('state', '=', 'pending')],
            order='create_date desc',
        )
        pending_received = Connection.search(
            [('connected_user_id', '=', user.id), ('state', '=', 'pending')],
            order='create_date desc',
        )
        return request.render(
            'club_social_profile.portal_my_connections',
            {
                'accepted': accepted,
                'pending_sent': pending_sent,
                'pending_received': pending_received,
                'page_name': 'my_connections',
            },
        )

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

    @http.route(
        '/api/connections/accept/<int:target_user_id>',
        type='http', auth='user', methods=['POST'], website=True, csrf=True,
    )
    def portal_connection_accept(self, target_user_id, **kwargs):
        """Accept the pending request `target_user_id` sent to the current user."""
        Connection = request.env['club_social_profile.connection'].sudo()
        redirect_base = f'/profile/{target_user_id}'
        conn = Connection.search([
            ('user_id', '=', target_user_id),
            ('connected_user_id', '=', request.env.user.id),
            ('state', '=', 'pending'),
        ], limit=1)
        if not conn:
            return request.redirect(f'{redirect_base}?error=no_pending_request')
        try:
            conn.action_accept()
        except (ValidationError, AccessError) as e:
            return request.redirect(f'{redirect_base}?{url_encode({"error": str(e)})}')
        except Exception:
            _logger.exception('Error accepting connection from user %s', target_user_id)
            return request.redirect(f'{redirect_base}?error=internal_error')
        return request.redirect(f'{redirect_base}?connection_accepted=1')

    @http.route(
        '/api/connections/remove/<int:target_user_id>',
        type='http', auth='user', methods=['POST'], website=True, csrf=True,
    )
    def portal_connection_remove(self, target_user_id, **kwargs):
        """Unfriend `target_user_id` — removes both reciprocal accepted rows."""
        Connection = request.env['club_social_profile.connection'].sudo()
        redirect_base = f'/profile/{target_user_id}'
        conn = Connection.search([
            ('user_id', '=', request.env.user.id),
            ('connected_user_id', '=', target_user_id),
            ('state', '=', 'accepted'),
        ], limit=1)
        if not conn:
            return request.redirect(f'{redirect_base}?error=not_connected')
        try:
            conn.action_unfriend()
        except (ValidationError, AccessError) as e:
            return request.redirect(f'{redirect_base}?{url_encode({"error": str(e)})}')
        except Exception:
            _logger.exception('Error removing connection with user %s', target_user_id)
            return request.redirect(f'{redirect_base}?error=internal_error')
        return request.redirect(f'{redirect_base}?connection_removed=1')
