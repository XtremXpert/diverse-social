from odoo import api, models

VALID_TYPES = frozenset({'profile', 'group', 'event', 'post', 'gallery'})
DEFAULT_LIMIT = 10
MAX_LIMIT = 50


class SocialSearchService(models.AbstractModel):
    _name = 'social_search.service'
    _description = 'Social Search Service'

    @api.model
    def _get_search_types(self):
        """Retourne l'ensemble des types de recherche valides. Extensible par héritage."""
        return set(VALID_TYPES)

    @api.model
    def search_all(self, query, limit=DEFAULT_LIMIT, offset=0, types=None):
        """Recherche unifiée. Retourne un dict {type: [résultats]}."""
        limit = min(int(limit), MAX_LIMIT)
        offset = int(offset)
        valid_types = self._get_search_types()
        active_types = (
            [t for t in types if t in valid_types]
            if types else list(valid_types)
        )
        _plural = {'gallery': 'galleries'}
        results = {}
        for t in active_types:
            plural = _plural.get(t, f'{t}s')
            results[t] = getattr(self, f'_search_{plural}')(query, limit, offset)
        return results

    # ── Profiles ──────────────────────────────────────────────────────────────

    @api.model
    def _search_profiles(self, query, limit, offset):
        user = self.env.user
        blocked_ids = self.env['social_safety.block'].get_blocked_ids_for(user)

        connection_user_ids = self.env['club_social_profile.connection'].search([
            ('user_id', '=', user.id),
            ('state', '=', 'accepted'),
        ]).mapped('connected_user_id.id')

        q = (query or '').strip()
        text_domain = (
            ['|', '|', '|',
             ('login', 'ilike', q),
             ('user_id.name', 'ilike', q),
             ('bio', 'ilike', q),
             ('city', 'ilike', q)]
            if q else []
        )

        visibility_domain = [
            '|',
            ('visibility', '=', 'members'),
            ('user_id', 'in', connection_user_ids),
        ]

        exclusion_domain = [('user_id', 'not in', blocked_ids)] if blocked_ids else []

        domain = text_domain + visibility_domain + exclusion_domain
        profiles = self.env['club_social_profile.profile'].search(
            domain, limit=limit, offset=offset
        )
        return [self._profile_to_dict(p) for p in profiles]

    def _profile_to_dict(self, p):
        return {
            'type': 'profile',
            'id': p.id,
            'user_id': p.user_id.id,
            'name': p.user_id.name,
            'login': p.login,
            'city': p.city or None,
            'bio': (p.bio or '')[:120] or None,
            'url': '/profile/%d' % p.user_id.id,
        }

    # ── Groups ────────────────────────────────────────────────────────────────

    @api.model
    def _search_groups(self, query, limit, offset):
        user = self.env.user
        q = (query or '').strip()
        text_domain = (
            ['|', ('name', 'ilike', q), ('description', 'ilike', q)]
            if q else []
        )
        # secret groups only visible to members
        visibility_domain = [
            '|',
            ('privacy', 'in', ['public', 'private']),
            ('member_ids', 'in', [user.id]),
        ]
        domain = text_domain + visibility_domain
        groups = self.env['social_group.group'].search(
            domain, limit=limit, offset=offset
        )
        return [self._group_to_dict(g) for g in groups]

    def _group_to_dict(self, g):
        return {
            'type': 'group',
            'id': g.id,
            'name': g.name,
            'description': (g.description or '')[:120] or None,
            'privacy': g.privacy,
            'member_count': g.member_count,
        }

    # ── Events ────────────────────────────────────────────────────────────────

    @api.model
    def _search_events(self, query, limit, offset):
        user = self.env.user
        q = (query or '').strip()
        text_domain = (
            ['|', ('name', 'ilike', q), ('description', 'ilike', q)]
            if q else []
        )
        # mirrors rule_event_social_visibility
        visibility_domain = [
            '|',
            ('social_visibility', '=', False),
            '|',
            ('social_visibility', '=', 'members'),
            ('allowed_circle_ids.member_ids', 'in', [user.id]),
        ]
        domain = text_domain + visibility_domain
        events = self.env['event.event'].search(
            domain, limit=limit, offset=offset, order='date_begin asc'
        )
        return [self._event_to_dict(e) for e in events]

    def _event_to_dict(self, e):
        return {
            'type': 'event',
            'id': e.id,
            'name': e.name,
            'date_begin': e.date_begin.isoformat() if e.date_begin else None,
            'date_end': e.date_end.isoformat() if e.date_end else None,
            'social_visibility': e.social_visibility or None,
            'organizer': e.organizer_user_id.name if e.organizer_user_id else None,
            'url': '/event/%d' % e.id,
        }

    # ── Posts ─────────────────────────────────────────────────────────────────

    @api.model
    def _search_posts(self, query, limit, offset):
        user = self.env.user
        blocked_ids = self.env['social_safety.block'].get_blocked_ids_for(user)

        q = (query or '').strip()
        text_domain = (
            ['|', ('name', 'ilike', q), ('content', 'ilike', q)]
            if q else []
        )
        visibility_domain = [
            ('state', '=', 'published'),
            '|',
            ('visibility', '=', 'public'),
            ('visibility', '=', 'members'),
        ]
        exclusion_domain = [('author_id', 'not in', blocked_ids)] if blocked_ids else []

        domain = text_domain + visibility_domain + exclusion_domain
        posts = self.env['social_base.post'].search(
            domain, limit=limit, offset=offset, order='create_date desc'
        )
        return [self._post_to_dict(p) for p in posts]

    def _post_to_dict(self, p):
        import re
        plain = re.sub(r'<[^>]+>', '', p.content or '')[:120] if p.content else None
        return {
            'type': 'post',
            'id': p.id,
            'name': p.name or None,
            'excerpt': plain or None,
            'author': p.author_id.name if p.author_id else None,
            'create_date': p.create_date.isoformat() if p.create_date else None,
            'visibility': p.visibility,
        }

    # ── Galleries ─────────────────────────────────────────────────────────────

    @api.model
    def _search_galleries(self, query, limit, offset):
        q = (query or '').strip()
        text_domain = (
            ['|', ('name', 'ilike', q), ('description', 'ilike', q)]
            if q else []
        )
        domain = text_domain + [('visibility', 'in', ['public', 'members'])]
        galleries = self.env['social_gallery.gallery'].search(
            domain, limit=limit, offset=offset, order='sequence, id'
        )
        return [self._gallery_to_dict(g) for g in galleries]

    def _gallery_to_dict(self, g):
        return {
            'type': 'gallery',
            'id': g.id,
            'name': g.name,
            'description': (g.description or '')[:120] or None,
            'photo_count': g.approved_photo_count,
            'is_shared': g.is_shared,
            'url': '/gallery/%d' % g.id,
        }
