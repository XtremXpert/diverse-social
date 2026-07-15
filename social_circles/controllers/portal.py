from werkzeug.exceptions import Forbidden

from odoo.exceptions import ValidationError
from odoo.http import request, route
from odoo.addons.portal.controllers.portal import CustomerPortal

_VALID_DETAIL_VIS = frozenset({'members', 'circles', 'specific', 'connections', 'private'})


class CirclesPortal(CustomerPortal):

    def _prepare_home_portal_values(self, counters):
        values = super()._prepare_home_portal_values(counters)
        if 'my_circles_count' in counters:
            profile = request.env['club_social_profile.profile'].sudo().search([
                ('user_id', '=', request.env.user.id),
            ], limit=1)
            values['my_circles_count'] = request.env['social_circles.circle'].search_count([
                ('profile_id', '=', profile.id),
            ]) if profile else 0
        return values

    # ── Page principale ───────────────────────────────────────────────────

    @route('/my/circles', auth='user', website=True)
    def my_circles(self, **kw):
        user = request.env.user
        profile = request.env['club_social_profile.profile'].get_or_create_for_user(user)
        circles = request.env['social_circles.circle'].search([
            ('profile_id', '=', profile.id),
        ], order='sequence, id')

        connections = _get_user_connections(user)
        circles_with_addable = []
        for circle in circles:
            in_circle = circle.sudo().member_ids
            addable = connections.filtered(lambda u: u not in in_circle)
            circles_with_addable.append((circle, addable))

        # Circles from other users where I am a member (read allowed via rule_circle_member_read)
        others_circles = request.env['social_circles.circle'].search([
            ('member_ids', 'in', user.id),
            ('profile_id.user_id', '!=', user.id),
        ], order='profile_id, sequence, id')

        # Pre-fetch member names with sudo() to avoid res.users record rules
        all_member_ids = set()
        for circle in circles:
            all_member_ids.update(circle.sudo().member_ids.ids)
        for oc in others_circles:
            all_member_ids.update(oc.sudo().member_ids.ids)
        member_name_map = {}
        if all_member_ids:
            Profile = request.env['club_social_profile.profile']
            for mu in request.env['res.users'].sudo().browse(list(all_member_ids)):
                # Pseudonyme (stealth_name) — jamais le vrai nom d'un membre.
                member_name_map[mu.id] = Profile._display_name_for_user(mu)

        # Circle types already used by this profile (to hide from the "add" list)
        used_type_ids = circles.mapped('type_id').ids
        available_types = request.env['social_circles.circle_type'].search([
            ('active', '=', True),
            ('id', 'not in', used_type_ids),
        ], order='sequence, id')

        # Invitations de cercle reçues (en attente de ma réponse).
        pending_invitations = request.env['social_circles.invitation'].sudo().search([
            ('invitee_user_id', '=', user.id),
            ('state', '=', 'pending'),
        ])

        return request.render('social_circles.portal_my_circles', {
            'circles': circles,
            'circles_with_addable': circles_with_addable,
            'others_circles': others_circles,
            'available_types': available_types,
            'profile': profile,
            'page_name': 'circles',
            'error': kw.get('error'),
            'member_name_map': member_name_map,
            'pending_invitations': pending_invitations,
        })

    # ── Create ─────────────────────────────────────────────────────────────

    @route('/my/circles/create', auth='user', methods=['GET', 'POST'], website=True, csrf=True)
    def circle_create(self, type_id='', name='', description='', **kw):
        """Create a circle from a type_id (required) with an optional nickname."""
        if request.httprequest.method == 'GET':
            return request.redirect('/my/circles')
        try:
            type_id = int(type_id)
        except (ValueError, TypeError):
            return request.redirect('/my/circles?error=type_required')
        circle_type = request.env['social_circles.circle_type'].sudo().browse(type_id).exists()
        if not circle_type:
            return request.redirect('/my/circles?error=type_required')
        profile = request.env['club_social_profile.profile'].get_or_create_for_user(request.env.user)
        # Savepoint so the INSERT rolls back when _check_unique_type raises.
        try:
            with request.env.cr.savepoint():
                request.env['social_circles.circle'].create({
                    'profile_id': profile.id,
                    'type_id': circle_type.id,
                    'name': (name or '').strip() or False,
                    'description': (description or '').strip() or False,
                })
        except ValidationError:
            return request.redirect('/my/circles?error=duplicate_type')
        return request.redirect('/my/circles?created=1')

    # ── Edit nom / description ─────────────────────────────────────────

    @route('/my/circles/<int:circle_id>/update', auth='user', methods=['POST'], website=True, csrf=True)
    def circle_update(self, circle_id, name='', description='', **kw):
        circle = _own_circle(circle_id)
        name = (name or '').strip()
        if not name:
            return request.redirect('/my/circles?error=name_required')
        try:
            with request.env.cr.savepoint():
                circle.sudo().write({
                    'name': name,
                    'description': description.strip() or False,
                })
        except ValidationError:
            return request.redirect('/my/circles?error=duplicate_name')
        return request.redirect('/my/circles?updated=1')

    # ── Supprimer ─────────────────────────────────────────────────────────

    @route('/my/circles/<int:circle_id>/delete', auth='user', methods=['POST'], website=True, csrf=True)
    def circle_delete(self, circle_id, **kw):
        circle = _own_circle(circle_id)
        circle.sudo().unlink()
        return request.redirect('/my/circles?deleted=1')

    # ── Ajouter un membre ─────────────────────────────────────────────────

    @route('/my/circles/<int:circle_id>/add_member', auth='user', methods=['POST'], website=True, csrf=True)
    def circle_add_member(self, circle_id, user_id=None, **kw):
        """Invite une connexion à rejoindre le cercle (avec son accord — décision
        produit : ranger quelqu'un dans un cercle passe toujours par une
        invitation, même entre connexions)."""
        circle = _own_circle(circle_id)
        if user_id:
            connections = _get_user_connections(request.env.user)
            member = request.env['res.users'].sudo().browse(int(user_id)).exists()
            if member and member in connections and member not in circle.sudo().member_ids:
                try:
                    with request.env.cr.savepoint():
                        request.env['social_circles.invitation'].sudo().create({
                            'circle_id': circle.id,
                            'inviter_user_id': request.env.user.id,
                            'invitee_user_id': member.id,
                        })
                except Exception:
                    return request.redirect('/my/circles?error=invite_failed')
        return request.redirect('/my/circles?invited=1')

    @route('/my/circles/invitations/<int:inv_id>/accept', auth='user',
           methods=['POST'], website=True, csrf=True)
    def circle_invitation_accept(self, inv_id, **kw):
        inv = request.env['social_circles.invitation'].sudo().browse(inv_id).exists()
        if not inv or inv.invitee_user_id != request.env.user:
            raise Forbidden()
        try:
            inv.with_user(request.env.user).action_accept()
        except Exception:
            return request.redirect('/my/circles?error=accept_failed')
        return request.redirect('/my/circles?joined=1')

    @route('/my/circles/invitations/<int:inv_id>/decline', auth='user',
           methods=['POST'], website=True, csrf=True)
    def circle_invitation_decline(self, inv_id, **kw):
        inv = request.env['social_circles.invitation'].sudo().browse(inv_id).exists()
        if not inv or inv.invitee_user_id != request.env.user:
            raise Forbidden()
        try:
            inv.with_user(request.env.user).action_decline()
        except Exception:
            pass
        return request.redirect('/my/circles?declined=1')

    # ── Retirer un membre ─────────────────────────────────────────────────

    @route('/my/circles/<int:circle_id>/remove_member', auth='user', methods=['POST'], website=True, csrf=True)
    def circle_remove_member(self, circle_id, user_id=None, **kw):
        circle = _own_circle(circle_id)
        if user_id:
            member = request.env['res.users'].sudo().browse(int(user_id)).exists()
            if member:
                circle.remove_member(member)
        return request.redirect('/my/circles')

    # ── Detailed profile visibility ────────────────────────────────────────

    @route('/my/circles/visibility', auth='user', methods=['POST'], website=True, csrf=True)
    def circle_visibility(self, detailed_visibility='members', detailed_visibility_circle_id='', **kw):
        if detailed_visibility not in _VALID_DETAIL_VIS:
            detailed_visibility = 'members'
        profile = request.env['club_social_profile.profile'].get_or_create_for_user(request.env.user)
        vals = {'detailed_visibility': detailed_visibility}
        if detailed_visibility == 'specific' and detailed_visibility_circle_id:
            try:
                circle_id = int(detailed_visibility_circle_id)
                circle = request.env['social_circles.circle'].sudo().browse(circle_id)
                if circle.exists() and circle.profile_id == profile:
                    vals['detailed_visibility_circle_id'] = circle_id
            except (ValueError, TypeError):
                pass
        else:
            vals['detailed_visibility_circle_id'] = False
        try:
            with request.env.cr.savepoint():
                profile.sudo().write(vals)
        except ValidationError:
            pass
        return request.redirect('/my/circles?vis_saved=1')


# ── Helpers module-level ──────────────────────────────────────────────────────

def _own_circle(circle_id):
    circle = request.env['social_circles.circle'].browse(circle_id).exists()
    if not circle or circle.profile_id.user_id != request.env.user:
        raise Forbidden()
    return circle


def _get_user_connections(user):
    """Return res.users with whom the user has an accepted connection."""
    Connection = request.env['club_social_profile.connection'].sudo()
    sent = Connection.search([('user_id', '=', user.id), ('state', '=', 'accepted')])
    recv = Connection.search([('connected_user_id', '=', user.id), ('state', '=', 'accepted')])
    user_ids = set(sent.mapped('connected_user_id.id')) | set(recv.mapped('user_id.id'))
    if not user_ids:
        return request.env['res.users'].sudo().browse()
    return request.env['res.users'].sudo().browse(list(user_ids))
