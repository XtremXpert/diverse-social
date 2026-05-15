from odoo.http import request, route
from odoo.addons.portal.controllers.portal import CustomerPortal, pager as portal_pager


_STEP = 24

_GENDER_LABELS = {
    'homme': 'Homme', 'femme': 'Femme',
    'trans_homme': 'Homme trans', 'trans_femme': 'Femme trans',
    'non_binaire': 'Non-binaire', 'autre': 'Autre',
    'non_specifie': 'Non spécifié',
}
_ORIENTATION_LABELS = {
    'hetero': 'Hétéro', 'gay': 'Gay / Lesbienne',
    'bi': 'Bisexuel·le', 'pan': 'Pansexuel·le',
    'asexuel': 'Asexuel·le', 'queer': 'Queer',
    'autre': 'Autre', 'non_specifie': 'Non spécifié',
}
_AVAILABILITY_LABELS = {
    'disponible': 'Disponible', 'couple_ouvert': 'Couple ouvert',
    'couple_ferme': 'Couple fermé', 'pas_disponible': 'Pas disponible',
    'non_specifie': 'Non spécifié',
}
_BDSM_ROLE_LABELS = {
    'dominant': 'Dominant·e', 'soumis': 'Soumis·e', 'switch': 'Switch',
    'maitre': 'Maître / Maîtresse', 'esclave': 'Esclave',
    'sadique': 'Sadique', 'masochiste': 'Masochiste',
    'curieux': 'Curieux·se', 'spectateur': 'Spectateur·trice', 'autre': 'Autre',
}


class DiscoverPortal(CustomerPortal):

    @route('/discover', auth='user', website=True)
    def discover(self, page=1, city='', gender='', orientation='',
                 availability='', bdsm_role='', **kw):
        user = request.env.user
        Profile = request.env['club_social_profile.profile'].sudo()

        # ── Utilisateurs bloqués ──────────────────────────────────────────
        blocked_ids = set()
        if 'social_safety.block' in request.env:
            blocked_ids = request.env['social_safety.block'].sudo().get_blocked_ids_for(user)

        # ── Connexions acceptées (pour panic mode + compat) ───────────────
        connected_user_ids = _get_connected_user_ids(user)

        # ── Profils en panic mode (non connectés exclus) ──────────────────
        panic_excluded_ids = set()
        if 'panic_mode' in request.env['club_social_profile.profile']._fields:
            panic_profiles = Profile.search([
                ('panic_mode', '=', True),
                ('user_id', 'not in', list(connected_user_ids | {user.id})),
            ])
            panic_excluded_ids = set(panic_profiles.mapped('user_id.id'))

        excluded_user_ids = (blocked_ids | panic_excluded_ids) - {user.id}

        # ── Domaine de base ───────────────────────────────────────────────
        domain = [
            ('user_id', '!=', user.id),
            ('visibility', '=', 'members'),
        ]
        if excluded_user_ids:
            domain.append(('user_id', 'not in', list(excluded_user_ids)))

        # ── Filtres ───────────────────────────────────────────────────────
        if city:
            domain.append(('city', 'ilike', city.strip()))
        if gender and gender in _GENDER_LABELS:
            domain.append(('gender', '=', gender))
        if orientation and orientation in _ORIENTATION_LABELS:
            domain.append(('orientation', '=', orientation))
        if availability and availability in _AVAILABILITY_LABELS:
            domain.append(('availability', '=', availability))
        has_bdsm = 'club_social_profile_bdsm.kink' in request.env
        if has_bdsm and bdsm_role and bdsm_role in _BDSM_ROLE_LABELS:
            domain.append(('bdsm_role', '=', bdsm_role))

        # ── Pagination ────────────────────────────────────────────────────
        url_args = {k: v for k, v in {
            'city': city, 'gender': gender, 'orientation': orientation,
            'availability': availability, 'bdsm_role': bdsm_role,
        }.items() if v}
        total = Profile.search_count(domain)
        pager = portal_pager(
            url='/discover', url_args=url_args,
            total=total, page=page, step=_STEP,
        )
        profiles = Profile.search(domain, limit=_STEP, offset=pager['offset'],
                                  order='profile_view_count desc, id desc')

        # ── Scores compatibilité BDSM ─────────────────────────────────────
        compat_map = {}
        if has_bdsm:
            my_profile = Profile.search([('user_id', '=', user.id)], limit=1)
            if my_profile and my_profile.bdsm_role:
                for p in profiles:
                    compat_map[p.id] = my_profile.compute_compatibility(p)

        return request.render('club_social_profile.portal_discover', {
            'profiles': profiles,
            'pager': pager,
            'total': total,
            'city': city,
            'gender': gender,
            'orientation': orientation,
            'availability': availability,
            'bdsm_role': bdsm_role,
            'has_bdsm': has_bdsm,
            'compat_map': compat_map,
            'connected_user_ids': connected_user_ids,
            'gender_labels': _GENDER_LABELS,
            'orientation_labels': _ORIENTATION_LABELS,
            'availability_labels': _AVAILABILITY_LABELS,
            'bdsm_role_labels': _BDSM_ROLE_LABELS,
            'page_name': 'discover',
        })


def _get_connected_user_ids(user):
    Connection = request.env['club_social_profile.connection'].sudo()
    sent = Connection.search([('user_id', '=', user.id), ('state', '=', 'accepted')])
    recv = Connection.search([('connected_user_id', '=', user.id), ('state', '=', 'accepted')])
    return set(sent.mapped('connected_user_id.id')) | set(recv.mapped('user_id.id'))
