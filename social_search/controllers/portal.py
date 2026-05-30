from odoo.http import request, route
from odoo.addons.portal.controllers.portal import CustomerPortal

_TYPE_LABELS = {
    'profile': 'Profils',
    'group': 'Groupes',
    'post': 'Publications',
    'gallery': 'Galeries',
    'event': 'Événements',
}

_ALL_TYPES = ['profile', 'group', 'post', 'gallery', 'event']


class SearchPortal(CustomerPortal):

    @route('/search', auth='user', website=True, sitemap=False)
    def search(self, q='', types=None, **kw):
        q = (q or '').strip()

        # Filtre de types : liste CSV ou liste multiple
        if isinstance(types, str):
            active_types = [t for t in types.split(',') if t in _ALL_TYPES] or None
        elif isinstance(types, list):
            active_types = [t for t in types if t in _ALL_TYPES] or None
        else:
            active_types = None  # tous

        results = {}
        total = 0
        if q:
            raw = request.env['social_search.service'].search_all(
                q, limit=8, types=active_types
            )
            results = raw
            total = sum(len(v) for v in raw.values())

        displayed_types = active_types or _ALL_TYPES

        return request.render('social_search.portal_search', {
            'q': q,
            'results': results,
            'total': total,
            'displayed_types': displayed_types,
            'active_types': active_types,
            'type_labels': _TYPE_LABELS,
            'all_types': _ALL_TYPES,
            'page_name': 'search',
        })
