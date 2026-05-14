from datetime import timedelta

from odoo import fields
from odoo.addons.portal.controllers.portal import CustomerPortal
from odoo.http import request, route
from odoo.exceptions import AccessError


class ProfilePortal(CustomerPortal):

    @route('/profile/<int:user_id>', auth='user', website=True, sitemap=False)
    def public_profile(self, user_id, **kw):
        viewer = request.env.user
        target_user = request.env['res.users'].sudo().browse(user_id)
        if not target_user.exists() or target_user.share:
            return request.not_found()

        profile = request.env['club_social_profile.profile'].sudo().search(
            [('user_id', '=', user_id)], limit=1
        )
        if not profile:
            return request.not_found()

        # Blocage → 404 (ne pas révéler l'existence)
        if 'social_safety.block' in request.env:
            if request.env['social_safety.block'].is_blocked(viewer, target_user):
                return request.not_found()

        is_own = viewer.id == user_id
        Connection = request.env['club_social_profile.connection'].sudo()
        is_connected = not is_own and (
            Connection.is_connected(viewer, target_user)
            or Connection.is_connected(target_user, viewer)
        )
        is_member = viewer.has_group('social_base.group_social_user')

        # Vérification visibilité
        if not is_own:
            if profile.visibility == 'connections' and not is_connected:
                display_name = profile.stealth_name or target_user.name
                return request.render('club_social_profile.portal_profile_restricted', {
                    'display_name': display_name,
                    'profile': profile,
                    'is_member': is_member,
                    'connection_state': _get_connection_state(Connection, viewer, target_user),
                })
            if not is_member:
                return request.render('club_social_profile.portal_profile_restricted', {
                    'display_name': profile.stealth_name or target_user.name,
                    'profile': profile,
                    'is_member': False,
                    'connection_state': None,
                })

        # Enregistrement visite (pas de self-visit, dédup 1h)
        if not is_own:
            _record_visit(profile, viewer)

        # État de connexion pour les boutons d'action
        connection_state = _get_connection_state(Connection, viewer, target_user) if not is_own else None

        # Posts récents publics/membres
        post_domain = [
            ('author_id', '=', viewer.id if is_own else user_id),
            ('state', '=', 'published'),
        ]
        if not is_own:
            post_domain.append(('visibility', 'in', ['public', 'members']))
        recent_posts = request.env['social_base.post'].sudo().search(
            post_domain, order='create_date desc', limit=6
        )

        # Galeries (optionnel)
        galleries = _get_galleries(profile, viewer, is_own, is_connected)

        # Connexions mutuelles (hors soi-même)
        mutual_connections = []
        if not is_own and is_connected:
            mutual_connections = _get_mutual_connections(Connection, viewer, target_user)

        display_name = target_user.name if is_own else (profile.stealth_name or target_user.name)

        values = {
            'profile': profile,
            'target_user': target_user,
            'display_name': display_name,
            'is_own': is_own,
            'is_connected': is_connected,
            'connection_state': connection_state,
            'recent_posts': recent_posts,
            'galleries': galleries,
            'mutual_connections': mutual_connections,
        }
        return request.render('club_social_profile.portal_profile_public', values)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _record_visit(profile, visitor):
    since = fields.Datetime.now() - timedelta(hours=1)
    existing = request.env['club_social_profile.profile_visit'].sudo().search([
        ('profile_id', '=', profile.id),
        ('visitor_id', '=', visitor.id),
        ('visited_at', '>=', since),
    ], limit=1)
    if not existing:
        request.env['club_social_profile.profile_visit'].sudo().create({
            'profile_id': profile.id,
            'visitor_id': visitor.id,
        })


def _get_connection_state(Connection, viewer, target_user):
    """Retourne: 'accepted', 'pending_sent', 'pending_received', ou None."""
    sent = Connection.search([
        ('user_id', '=', viewer.id),
        ('connected_user_id', '=', target_user.id),
    ], limit=1)
    if sent:
        return 'accepted' if sent.state == 'accepted' else 'pending_sent'
    received = Connection.search([
        ('user_id', '=', target_user.id),
        ('connected_user_id', '=', viewer.id),
    ], limit=1)
    if received:
        return 'accepted' if received.state == 'accepted' else 'pending_received'
    return None


def _get_galleries(profile, viewer, is_own, is_connected):
    if 'social_gallery.gallery' not in request.env:
        return request.env['social_gallery.gallery'].browse() if False else []
    domain = [('owner_id', '=', profile.user_id.id)]
    if not is_own:
        if is_connected:
            domain.append(('visibility', 'in', ['public', 'members', 'connections']))
        else:
            domain.append(('visibility', 'in', ['public', 'members']))
    return request.env['social_gallery.gallery'].sudo().search(domain, limit=6)


def _get_mutual_connections(Connection, viewer, target_user):
    """Retourne jusqu'à 6 profils connectés aux deux utilisateurs."""
    viewer_connected_ids = set(Connection.search([
        ('user_id', '=', viewer.id), ('state', '=', 'accepted'),
    ]).mapped('connected_user_id.id')) | set(Connection.search([
        ('connected_user_id', '=', viewer.id), ('state', '=', 'accepted'),
    ]).mapped('user_id.id'))

    target_connected_ids = set(Connection.search([
        ('user_id', '=', target_user.id), ('state', '=', 'accepted'),
    ]).mapped('connected_user_id.id')) | set(Connection.search([
        ('connected_user_id', '=', target_user.id), ('state', '=', 'accepted'),
    ]).mapped('user_id.id'))

    mutual_ids = list(viewer_connected_ids & target_connected_ids)[:6]
    if not mutual_ids:
        return []
    return request.env['club_social_profile.profile'].sudo().search([
        ('user_id', 'in', mutual_ids),
    ])
