from datetime import timedelta

from odoo import fields
from odoo.addons.portal.controllers.portal import CustomerPortal
from odoo.http import request, route


class DashboardPortal(CustomerPortal):

    @route('/my/dashboard', auth='user', website=True, sitemap=False)
    def dashboard(self, **kw):
        user = request.env.user
        now = fields.Datetime.now()
        since = now - timedelta(days=7)

        profile = request.env['club_social_profile.profile'].sudo().search(
            [('user_id', '=', user.id)], limit=1
        )

        # ── Weekly stats ──────────────────────────────────────────────────────
        profile_views = 0
        if profile:
            profile_views = request.env['club_social_profile.profile_visit'].sudo().search_count([
                ('profile_id', '=', profile.id),
                ('visited_at', '>=', since),
            ])

        new_connections = request.env['club_social_profile.connection'].sudo().search_count([
            '|',
            '&', ('user_id', '=', user.id), ('state', '=', 'accepted'),
            '&', ('connected_user_id', '=', user.id), ('state', '=', 'accepted'),
            ('write_date', '>=', since),
        ])

        pending_requests = request.env['club_social_profile.connection'].sudo().search_count([
            ('connected_user_id', '=', user.id),
            ('state', '=', 'pending'),
        ])

        unread_notifs = request.env['club_social_profile.notification'].sudo().search_count([
            ('user_id', '=', user.id),
            ('is_read', '=', False),
        ])

        # ── My active groups ──────────────────────────────────────────────────
        my_groups = []
        if 'social_group.group' in request.env:
            my_groups = request.env['social_group.group'].sudo().search([
                ('member_ids', 'in', [user.id]),
            ], limit=6)

        # ── Proposals open for voting ─────────────────────────────────────────
        proposals_voting = []
        if 'social_governance.proposal' in request.env:
            proposals_voting = request.env['social_governance.proposal'].sudo().search([
                ('state', '=', 'voting'),
            ], order='voting_closes_at asc', limit=4)

        # ── Upcoming events ───────────────────────────────────────────────────
        upcoming_events = []
        if 'event.event' in request.env:
            upcoming_events = request.env['event.event'].sudo().search([
                ('date_begin', '>=', now),
                ('date_begin', '<=', now + timedelta(days=14)),
            ], order='date_begin asc', limit=4)

        # ── Recent notifications ──────────────────────────────────────────────
        recent_notifs = request.env['club_social_profile.notification'].sudo().search([
            ('user_id', '=', user.id),
        ], order='create_date desc', limit=5)

        # ── Recent connections ────────────────────────────────────────────────
        recent_conn_ids = request.env['club_social_profile.connection'].sudo().search([
            '|',
            '&', ('user_id', '=', user.id), ('state', '=', 'accepted'),
            '&', ('connected_user_id', '=', user.id), ('state', '=', 'accepted'),
            ('write_date', '>=', since),
        ], limit=6)
        recent_conn_user_ids = set()
        for c in recent_conn_ids:
            other = c.connected_user_id if c.user_id.id == user.id else c.user_id
            recent_conn_user_ids.add(other.id)
        recent_conn_profiles = request.env['club_social_profile.profile'].sudo().search([
            ('user_id', 'in', list(recent_conn_user_ids)),
        ])

        _NOTIF_ICONS = {
            'connection_request': '🤝', 'connection_accepted': '✅',
            'post_like': '❤️', 'post_comment': '💬', 'new_message': '✉️',
            'profile_visit': '👁️', 'proposal_voting': '🗳️',
            'group_join_request': '👥', 'group_join_approved': '✅',
            'gallery_photo_approved': '🖼️', 'circle_added': '🔵',
        }

        return request.render('club_social_profile.portal_dashboard', {
            'profile': profile,
            'profile_views': profile_views,
            'new_connections': new_connections,
            'pending_requests': pending_requests,
            'unread_notifs': unread_notifs,
            'my_groups': my_groups,
            'proposals_voting': proposals_voting,
            'upcoming_events': upcoming_events,
            'recent_notifs': recent_notifs,
            'recent_conn_profiles': recent_conn_profiles,
            'notif_icons': _NOTIF_ICONS,
        })
