import json

from odoo.http import request, route, Controller

# Cap returned points per request — keeps payloads under a few hundred KB
# and prevents a moderator from accidentally pulling thousands at once.
_MAP_RESULT_CAP = 500


class MembersMapPortal(Controller):

    @route('/members/map', auth='user', website=True, sitemap=False)
    def members_map(self, **kw):
        user = request.env.user
        if not user.has_group('social_base.group_social_user'):
            return request.redirect('/web')

        is_moderator = user.has_group('social_base.group_social_moderator')
        my_profile = request.env['club_social_profile.profile'].sudo().search(
            [('user_id', '=', user.id)], limit=1,
        )

        if not is_moderator and not my_profile.show_on_map:
            return request.render('social_discovery.members_map_opt_in_required', {
                'profile': my_profile,
            })

        return request.render('social_discovery.members_map_page', {
            'is_moderator': is_moderator,
            'profile': my_profile,
        })

    @route('/members/map.json', auth='user', type='http', methods=['GET'], csrf=False)
    def members_map_json(self, bbox=None, **kw):
        user = request.env.user
        if not user.has_group('social_base.group_social_user'):
            return _json({'error': 'forbidden'}, status=403)

        is_moderator = user.has_group('social_base.group_social_moderator')
        my_profile = request.env['club_social_profile.profile'].sudo().search(
            [('user_id', '=', user.id)], limit=1,
        )
        if not is_moderator and not my_profile.show_on_map:
            return _json({'error': 'opt_in_required'}, status=403)

        bounds = _parse_bbox(bbox)

        domain = [
            ('geo_status', '=', 'done'),
            ('user_id', '!=', user.id),
            ('user_id.active', '=', True),
            ('user_id.all_group_ids', 'in', [user.env.ref('social_base.group_social_user').id]),
        ]
        if not is_moderator:
            # Moderators see opted-out profiles too (for territory exclusions);
            # everyone else only sees opted-in members.
            domain.append(('show_on_map', '=', True))
            domain.append(('visibility', '=', 'members'))

        if bounds:
            lat_min, lng_min, lat_max, lng_max = bounds
            domain += [
                ('geo_lat_jitter', '>=', lat_min),
                ('geo_lat_jitter', '<=', lat_max),
                ('geo_lng_jitter', '>=', lng_min),
                ('geo_lng_jitter', '<=', lng_max),
            ]

        # Bidirectional block filter — runtime check, social_safety may be
        # uninstalled in some deploys.
        if 'social_safety.block' in request.env:
            blocked_ids = request.env['social_safety.block'].get_blocked_ids_for(user)
            if blocked_ids:
                domain.append(('user_id', 'not in', list(blocked_ids)))

        Profile = request.env['club_social_profile.profile'].sudo()
        profiles = Profile.search(domain, limit=_MAP_RESULT_CAP)

        # Consent-gate filter: if a gate is active and the searcher hasn't
        # been approved, hide the profile from the map entirely.
        if 'social_consent.gate' in request.env:
            Gate = request.env['social_consent.gate'].sudo()
            Req = request.env['social_consent.request'].sudo()
            allowed = []
            for p in profiles:
                gate = Gate.search([('profile_id', '=', p.id), ('is_active', '=', True)], limit=1)
                if not gate:
                    allowed.append(p)
                    continue
                approved = Req.search_count([
                    ('gate_id', '=', gate.id),
                    ('requester_id', '=', user.id),
                    ('state', '=', 'approved'),
                ])
                if approved:
                    allowed.append(p)
            profiles = profiles.browse([p.id for p in allowed])

        # Never expose user.login (≈ email PII). Use stealth_name → user.name,
        # and link to the profile page by user_id (the canonical /profile/<int> route).
        points = [{
            'id': p.id,
            'user_id': p.user_id.id,
            'lat': p.geo_lat_jitter,
            'lng': p.geo_lng_jitter,
            'name': p.stealth_name or p.user_id.name or '',
            'city': p.city or '',
        } for p in profiles]

        return _json({'success': True, 'count': len(points), 'points': points})


def _parse_bbox(raw):
    """Accept 'lat_min,lng_min,lat_max,lng_max'. Return tuple or None."""
    if not raw:
        return None
    try:
        parts = [float(x) for x in raw.split(',')]
    except (TypeError, ValueError):
        return None
    if len(parts) != 4:
        return None
    lat_min, lng_min, lat_max, lng_max = parts
    if lat_min > lat_max or lng_min > lng_max:
        return None
    if not (-90 <= lat_min <= 90 and -90 <= lat_max <= 90):
        return None
    if not (-180 <= lng_min <= 180 and -180 <= lng_max <= 180):
        return None
    return (lat_min, lng_min, lat_max, lng_max)


def _json(payload, status=200):
    return request.make_response(
        json.dumps(payload),
        headers=[('Content-Type', 'application/json')],
        status=status,
    )
