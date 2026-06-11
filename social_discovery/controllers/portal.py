from datetime import date

from odoo.addons.portal.controllers.portal import CustomerPortal, pager as portal_pager
from odoo.http import request, route

_PAGE_SIZE = 24
_SORT_MAP = {
    'recent':  'write_date desc',
    'new':     'create_date desc',
    'alpha':   'login asc',
}
_SORT_DEFAULT = 'recent'

# sort='compat' is a special case: the score is computed in Python, so we
# can't use SQL ORDER BY. We fetch a buffer of candidates, score them all,
# then paginate the sorted result in Python. The buffer cap is the upper
# bound on the candidate pool — beyond it, the sort becomes partial. For
# the foreseeable membership size this is a non-issue; document and
# revisit if /members ever returns > _COMPAT_BUFFER_CAP candidates.
_COMPAT_BUFFER_CAP = 500
_COMPAT_SORT = 'compat'


class MembersPortal(CustomerPortal):

    @route(['/members', '/members/page/<int:page>'], auth='user', website=True, sitemap=False)
    def members(self, page=1, sort=None, q='', **kw):
        user = request.env.user
        if not user.has_group('social_base.group_social_user'):
            return request.redirect('/web')

        valid_sorts = set(_SORT_MAP) | {_COMPAT_SORT}
        sort = sort if sort in valid_sorts else _SORT_DEFAULT
        page = max(1, int(page))

        # Filters from GET parameters (multi-value via getlist)
        args = request.httprequest.args
        genders       = args.getlist('gender')
        orientations  = args.getlist('orientation')
        availabilities = args.getlist('availability')
        bdsm_roles    = args.getlist('bdsm_role')
        experiences   = args.getlist('experience')
        has_photo     = args.get('has_photo') == '1'
        city          = args.get('city', '').strip()
        min_age       = _int_or(args.get('min_age'), 18)
        max_age       = _int_or(args.get('max_age'), 0)
        min_compat    = max(0, min(_int_or(args.get('min_compat'), 0), 100))

        domain = _build_domain(
            user, q, genders, orientations, availabilities,
            bdsm_roles, experiences, has_photo, city, min_age, max_age,
        )

        Profile = request.env['club_social_profile.profile'].sudo()
        Profile_base = request.env['club_social_profile.profile']
        has_bdsm = 'bdsm_role' in Profile_base._fields

        # sort=compat is only meaningful when the BDSM scoring exists. Fall
        # back to the default sort silently otherwise.
        if sort == _COMPAT_SORT and not has_bdsm:
            sort = _SORT_DEFAULT

        url_args = dict(
            sort=sort, q=q,
            **{k: v for k, v in args.items(multi=True) if k not in ('sort', 'q', 'page')},
        )

        compat_scores = {}

        if sort == _COMPAT_SORT:
            # ── Python-paginated compatibility sort ──────────────────────────
            # The score isn't a stored column, so we fetch a bounded buffer,
            # score everything, filter on min_compat, then slice in Python.
            # Pager total reflects the *filtered* count (what the user can
            # actually browse), not the unfiltered candidate pool.
            my_profile = Profile.search([('user_id', '=', user.id)], limit=1)
            buffer_profiles = Profile.search(
                domain, order='write_date desc', limit=_COMPAT_BUFFER_CAP,
            )
            # Warm the cache once for all candidates.
            buffer_profiles.mapped('kink_level_ids')
            if my_profile:
                my_profile.mapped('kink_level_ids')

            scored = []
            for p in buffer_profiles:
                if not my_profile:
                    score = 0
                else:
                    try:
                        score = my_profile.compute_compatibility(p)['score']
                    except Exception:
                        score = 0
                if score < min_compat:
                    continue
                scored.append((score, p.id))
                compat_scores[p.id] = score

            # Stable sort: tie-break on id to keep the order deterministic
            # across page navigations.
            scored.sort(key=lambda x: (-x[0], x[1]))

            total = len(scored)
            pager = portal_pager(
                url='/members', url_args=url_args,
                total=total, page=page, step=_PAGE_SIZE,
            )
            page_ids = [pid for _, pid in scored[pager['offset']:pager['offset'] + _PAGE_SIZE]]
            # browse() preserves order from the id list.
            profiles = Profile.browse(page_ids)
        else:
            # ── SQL-paginated sort (recent / new / alpha) ─────────────────────
            total = Profile.search_count(domain)
            pager = portal_pager(
                url='/members', url_args=url_args,
                total=total, page=page, step=_PAGE_SIZE,
            )
            profiles = Profile.search(
                domain,
                order=_SORT_MAP[sort],
                limit=_PAGE_SIZE,
                offset=pager['offset'],
            )

            # Per-page compatibility scoring (existing behaviour).
            if has_bdsm and profiles:
                my_profile = Profile.search([('user_id', '=', user.id)], limit=1)
                if my_profile:
                    profiles.mapped('kink_level_ids')
                    my_profile.mapped('kink_level_ids')
                    for p in profiles:
                        try:
                            compat_scores[p.id] = my_profile.compute_compatibility(p)['score']
                        except Exception:
                            compat_scores[p.id] = 0
                if min_compat:
                    profiles = profiles.filtered(
                        lambda p: compat_scores.get(p.id, 0) >= min_compat
                    )

        genders_opts      = request.env['social_discovery.gender_value'].sudo().search([])
        orientations_opts = request.env['social_discovery.orientation_value'].sudo().search([])
        avail_opts        = request.env['social_discovery.availability_value'].sudo().search([])
        kinks_opts        = (
            request.env['club_social_profile_bdsm.kink'].sudo().search([('active', '=', True)])
            if 'club_social_profile_bdsm.kink' in request.env else []
        )

        from odoo import _
        _ROLE_LABELS = {
            'dominant': _('Dominant'), 'soumis': _('Submissive'), 'switch': _('Switch'),
            'maitre': _('Master/Mistress'), 'esclave': _('Slave'),
            'sadique': _('Sadist'), 'masochiste': _('Masochist'),
            'curieux': _('Curious'), 'spectateur': _('Spectator'), 'autre': _('Other'),
        }
        _EXP_LABELS = {
            'nouveau': _('New'), 'intermediate': _('Intermediate'),
            'experimente': _('Experienced'),
        }

        values = {
            'profiles': profiles,
            'pager': pager,
            'total': total,
            'sort': sort,
            'q': q,
            # active filters
            'active_genders': genders,
            'active_orientations': orientations,
            'active_availabilities': availabilities,
            'active_bdsm_roles': bdsm_roles,
            'active_experiences': experiences,
            'active_has_photo': has_photo,
            'active_city': city,
            'active_min_age': min_age,
            'active_max_age': max_age,
            'active_min_compat': min_compat,
            'compat_scores': compat_scores,
            # dropdown options
            'genders_opts': genders_opts,
            'orientations_opts': orientations_opts,
            'avail_opts': avail_opts,
            'kinks_opts': kinks_opts,
            'has_bdsm': has_bdsm,
            'role_labels': _ROLE_LABELS,
            'exp_labels': _EXP_LABELS,
        }
        return request.render('social_discovery.portal_members', values)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _int_or(val, default):
    try:
        return int(val)
    except (TypeError, ValueError):
        return default


def _build_domain(user, q, genders, orientations, availabilities,
                  bdsm_roles, experiences, has_photo, city, min_age, max_age):
    current_year = date.today().year

    # Exclude blocked users
    blocked_ids = []
    if 'social_safety.block' in request.env:
        blocked_ids = request.env['social_safety.block'].get_blocked_ids_for(user)

    # After the portal/internal refactor, club members are portal users
    # (share=True). We filter on social_user group membership instead.
    domain = [
        ('user_id', '!=', user.id),
        ('user_id.active', '=', True),
        ('user_id.all_group_ids', 'in', [user.env.ref('social_base.group_social_user').id]),
        ('onboarding_done', '=', True),
        ('visibility', '=', 'members'),
    ]
    if blocked_ids:
        domain.append(('user_id', 'not in', blocked_ids))

    if q:
        domain += ['|', '|',
                   ('user_id.name', 'ilike', q),
                   ('bio', 'ilike', q),
                   ('city', 'ilike', q)]

    if city:
        domain.append(('city', 'ilike', city))

    if genders:
        domain.append(('gender', 'in', genders))
    if orientations:
        domain.append(('orientation', 'in', orientations))
    if availabilities:
        domain.append(('availability', 'in', availabilities))

    if has_photo:
        domain.append(('profile_image', '!=', False))

    # Age filters → convert to birth_year
    if min_age and min_age > 18:
        domain += [('birth_year', '!=', 0), ('birth_year', '<=', current_year - min_age)]
    if max_age:
        domain += [('birth_year', '!=', 0), ('birth_year', '>=', current_year - max_age)]

    # BDSM filters (optional, only if the module is installed)
    Profile_fields = request.env['club_social_profile.profile']._fields
    if bdsm_roles and 'bdsm_role' in Profile_fields:
        domain.append(('bdsm_role', 'in', bdsm_roles))
    if experiences and 'experience' in Profile_fields:
        domain.append(('experience', 'in', experiences))

    return domain
