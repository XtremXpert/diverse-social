from odoo import _
from odoo.http import request, route
from odoo.addons.portal.controllers.portal import CustomerPortal, pager as portal_pager


_STEP = 24


def _gender_labels():
    return {
        'homme': _('Man'), 'femme': _('Woman'),
        'trans_homme': _('Trans man'), 'trans_femme': _('Trans woman'),
        'non_binaire': _('Non-binary'), 'autre': _('Other'),
        'non_specifie': _('Unspecified'),
    }


def _orientation_labels():
    return {
        'hetero': _('Heterosexual'), 'gay': _('Gay / Lesbian'),
        'bi': _('Bisexual'), 'pan': _('Pansexual'),
        'asexuel': _('Asexual'), 'queer': _('Queer'),
        'autre': _('Other'), 'non_specifie': _('Unspecified'),
    }


def _availability_labels():
    return {
        'disponible': _('Available'), 'couple_ouvert': _('Open couple'),
        'couple_ferme': _('Closed couple'), 'pas_disponible': _('Not available'),
        'non_specifie': _('Unspecified'),
    }


def _bdsm_role_labels():
    return {
        'dominant': _('Dominant'), 'soumis': _('Submissive'), 'switch': _('Switch'),
        'maitre': _('Master / Mistress'), 'esclave': _('Slave'),
        'sadique': _('Sadist'), 'masochiste': _('Masochist'),
        'curieux': _('Curious'), 'spectateur': _('Spectator'), 'autre': _('Other'),
    }


class DiscoverPortal(CustomerPortal):

    @route(['/discover', '/discover/page/<int:page>'], auth='user', website=True)
    def discover(self, page=1, city='', gender='', orientation='',
                 availability='', bdsm_role='', **kw):
        user = request.env.user
        Profile = request.env['club_social_profile.profile'].sudo()
        gender_labels = _gender_labels()
        orientation_labels = _orientation_labels()
        availability_labels = _availability_labels()
        bdsm_role_labels = _bdsm_role_labels()

        # ── Blocked users ─────────────────────────────────────────────────
        blocked_ids = set()
        if 'social_safety.block' in request.env:
            blocked_ids = request.env['social_safety.block'].sudo().get_blocked_ids_for(user)

        # ── Accepted connections (for panic mode + compatibility) ─────────
        connected_user_ids = _get_connected_user_ids(user)

        # ── Profiles in panic mode (exclude non-connected ones) ───────────
        panic_excluded_ids = set()
        if 'panic_mode' in request.env['club_social_profile.profile']._fields:
            panic_profiles = Profile.search([
                ('panic_mode', '=', True),
                ('user_id', 'not in', list(connected_user_ids | {user.id})),
            ])
            panic_excluded_ids = set(panic_profiles.mapped('user_id.id'))

        excluded_user_ids = (blocked_ids | panic_excluded_ids) - {user.id}

        # ── Base domain ───────────────────────────────────────────────────
        # Listing membres : restreint aux users qui sont *effectivement*
        # membres du réseau (i.e. ont group_social_user). Un user système
        # ou un modérateur qui se trouve à avoir un profile (créé par
        # `get_or_create_for_user` lors d'une visite admin) ne doit PAS
        # apparaître dans /discover — sa présence dans le listing donne
        # l'illusion qu'il fait partie de la communauté alors qu'il n'est
        # ni parrainé ni assujetti aux mêmes règles.
        social_group_id = request.env.ref('social_base.group_social_user').id
        domain = [
            ('user_id', '!=', user.id),
            ('visibility', '=', 'members'),
            ('user_id.all_group_ids', 'in', [social_group_id]),
        ]
        if excluded_user_ids:
            domain.append(('user_id', 'not in', list(excluded_user_ids)))

        # ── Filters ───────────────────────────────────────────────────────
        if city:
            domain.append(('city', 'ilike', city.strip()))
        if gender and gender in gender_labels:
            domain.append(('gender', '=', gender))
        if orientation and orientation in orientation_labels:
            domain.append(('orientation', '=', orientation))
        if availability and availability in availability_labels:
            domain.append(('availability', '=', availability))
        has_bdsm = 'club_social_profile_bdsm.kink' in request.env
        if has_bdsm and bdsm_role and bdsm_role in bdsm_role_labels:
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

        # ── BDSM compatibility scores ─────────────────────────────────────
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
            'gender_labels': gender_labels,
            'orientation_labels': orientation_labels,
            'availability_labels': availability_labels,
            'bdsm_role_labels': bdsm_role_labels,
            'page_name': 'discover',
        })


def _get_connected_user_ids(user):
    Connection = request.env['club_social_profile.connection'].sudo()
    sent = Connection.search([('user_id', '=', user.id), ('state', '=', 'accepted')])
    recv = Connection.search([('connected_user_id', '=', user.id), ('state', '=', 'accepted')])
    return set(sent.mapped('connected_user_id.id')) | set(recv.mapped('user_id.id'))
