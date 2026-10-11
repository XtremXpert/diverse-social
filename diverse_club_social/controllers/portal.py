from datetime import timedelta

from odoo import fields
from odoo.addons.social_age_gate.controllers.portal import AgeGatePortal, _get_profile
from odoo.http import request, route


class DiversePortal(AgeGatePortal):
    """Diverse-Cité — /my devient le tableau de bord.

    Auparavant /my rendait une grille de cartes-raccourcis qui dupliquait
    intégralement la navigation (Groups, Circles, Safety, Membership… déjà
    présents dans le menu « Mon réseau »). On retire cette grille : /my (et
    /my/home) redirigent vers le tableau de bord, qui devient la vraie page
    d'atterrissage du portail — un *bilan* (stats hebdo + activité) plus un
    bloc « Mon compte » (gestion/facturation, absente de la nav).

    Hérite de AgeGatePortal (et non CustomerPortal) pour que les gates
    age + onboarding s'appliquent AVANT la redirection vers le dashboard :
    sans cela, un membre non vérifié contournait l'age gate (Loi 25).
    """

    # ── /my & /my/home → tableau de bord (après les gates) ────────────────
    @route(['/my', '/my/home'], type='http', auth='user', website=True)
    def home(self, **kw):
        profile = _get_profile(request.env.user)
        if profile and not profile.age_gate_passed:
            return request.redirect('/age-verify')
        if (not request.session.get('onboarding_prompted')
                and getattr(request.env.user.partner_id.sudo(), 'member_state', None) == 'active'
                and profile and not profile.onboarding_done):
            request.session['onboarding_prompted'] = True
            return request.redirect('/onboarding')
        return request.redirect('/my/dashboard')

    # ── Tableau de bord en charte Diverse-Cité ────────────────────────────
    # NB : la collecte de données reprend celle de
    # club_social_profile.controllers.portal_dashboard.DashboardPortal
    # (submodule pinné `bemade/social`). On la duplique ici pour pouvoir
    # rendre NOTRE template (hero + charte + bloc compte) et ajouter l'état
    # d'adhésion, sans modifier le submodule. À garder synchro lors d'un bump.
    @route('/my/dashboard', auth='user', website=True, sitemap=False)
    def dashboard(self, **kw):
        user = request.env.user
        now = fields.Datetime.now()
        since = now - timedelta(days=7)

        profile = request.env['club_social_profile.profile'].sudo().search(
            [('user_id', '=', user.id)], limit=1
        )

        # ── Stats hebdo ──────────────────────────────────────────────────
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

        # ── Mes groupes actifs ───────────────────────────────────────────
        my_groups = []
        if 'social_group.group' in request.env:
            my_groups = request.env['social_group.group'].sudo().search([
                ('member_ids', 'in', [user.id]),
            ], limit=6)

        # ── Propositions ouvertes au vote ────────────────────────────────
        proposals_voting = []
        if 'social_governance.proposal' in request.env:
            proposals_voting = request.env['social_governance.proposal'].sudo().search([
                ('state', '=', 'voting'),
            ], order='voting_closes_at asc', limit=4)

        # ── Événements à venir ───────────────────────────────────────────
        upcoming_events = []
        if 'event.event' in request.env:
            upcoming_events = request.env['event.event'].sudo().search([
                ('date_begin', '>=', now),
                ('date_begin', '<=', now + timedelta(days=14)),
            ], order='date_begin asc', limit=4)

        # ── Notifications récentes ───────────────────────────────────────
        recent_notifs = request.env['club_social_profile.notification'].sudo().search([
            ('user_id', '=', user.id),
        ], order='create_date desc', limit=5)

        # ── Nouvelles connexions ─────────────────────────────────────────
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

        # ── Bloc « Mon compte » : état d'adhésion + facturation ──────────
        partner = user.partner_id
        member_state = partner.member_state if 'member_state' in partner._fields else False
        invoice_count = request.env['account.move'].sudo().search_count([
            ('partner_id', '=', partner.id),
            ('move_type', 'in', ('out_invoice', 'out_refund')),
            ('state', '=', 'posted'),
        ]) if 'account.move' in request.env else 0

        return request.render('diverse_club_social.portal_dashboard_diverse', {
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
            'member_state': member_state,
            'invoice_count': invoice_count,
        })

    # ── Hub Communauté — page d'accueil du réseau social ────────────────
    @route('/community', auth='user', website=True, sitemap=False)
    def community_hub(self, **kw):
        """Page hub du réseau social avec liens vers les sections principales."""
        return request.render('diverse_club_social.community_hub', {})
