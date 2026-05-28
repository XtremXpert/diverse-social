import math
import re
from collections import defaultdict
from datetime import datetime, timezone

from odoo import api, fields, models

DEFAULT_LIMIT = 20
MAX_LIMIT = 100
VALID_TYPES = frozenset({'post', 'story', 'event', 'event_registration', 'proposal', 'gallery'})

# Relevance scoring constants
_FEED_GRAVITY = 1.2       # decay exponent — higher = faster drop-off
_HALF_LIFE_HOURS = 24.0   # hours for content value to halve (before engagement/boosts)


def _parse_ts(ts_str):
    """Parse ISO timestamp string to UTC-aware datetime, or None on failure."""
    if not ts_str:
        return None
    try:
        dt = datetime.fromisoformat(ts_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        return None


class SocialFeedService(models.AbstractModel):
    _name = 'social_feed.service'
    _description = 'Social Feed Service'

    @api.model
    def _get_feed_types(self):
        """Retourne l'ensemble des types de feed valides. Extensible par héritage."""
        return set(VALID_TYPES)

    @api.model
    def _get_feed_dispatch(self):
        """Retourne le mapping type → méthode. Extensible par héritage."""
        return {
            'post': self._feed_posts,
            'story': self._feed_stories,
            'event': self._feed_events,
            'event_registration': self._feed_event_registrations,
            'proposal': self._feed_proposals,
            'gallery': self._feed_gallery,
        }

    @api.model
    def get_feed(self, limit=DEFAULT_LIMIT, offset=0, types=None, sort='recent'):
        """Retourne le fil d'actualité de l'utilisateur courant.

        sort='recent'    — tri chronologique DESC (comportement historique, défaut)
        sort='relevance' — tri algorithmique : recency × engagement × connexion × type

        Note : chaque type est fetché depuis sa propre table dans un buffer limité.
        Avec sort='relevance', du contenu populaire mais hors-buffer peut être absent.
        Le buffer est agrandi automatiquement pour atténuer cet effet.
        """
        limit = min(int(limit), MAX_LIMIT)
        offset = int(offset)
        valid_types = self._get_feed_types()
        active_types = (
            [t for t in types if t in valid_types] if types else list(valid_types)
        )

        # Buffer plus généreux en mode relevance pour capturer du contenu engageant
        # qui serait autrement écarté par le tri chronologique natif de chaque source.
        if sort == 'relevance':
            fetch_n = (limit + offset) * 3 + 50
        else:
            fetch_n = (limit + offset) * 2 + 20

        ctx = self._feed_context()

        items = []
        dispatch = self._get_feed_dispatch()
        for t in active_types:
            items.extend(dispatch[t](ctx, fetch_n))

        if sort == 'relevance':
            now = datetime.now(tz=timezone.utc)
            connection_set = set(ctx['connection_user_ids'])
            for item in items:
                item['score'] = self._score_item(item, ctx, now, connection_set)
            items.sort(key=lambda x: (x['score'], x['timestamp']), reverse=True)
        else:
            items.sort(key=lambda x: x['timestamp'], reverse=True)

        page = items[offset: offset + limit]
        self._annotate_read_state(page, ctx['user'])

        return {
            'items': page,
            'has_more': len(items) > offset + limit,
        }

    # ── Read state ────────────────────────────────────────────────────────────

    @api.model
    def _annotate_read_state(self, items, user):
        """Set 'is_read': bool on each item in the slice.

        One batched query against social_feed.read_marker regardless of
        page size, scoped to (item_type, item_id) pairs in the slice.
        """
        if not items:
            return
        read_set = self.env['social_feed.read_marker'].sudo().read_set_for_user(
            user.id, items=items,
        )
        for it in items:
            it['is_read'] = (it.get('item_type'), it.get('id')) in read_set

    # ── Relevance scoring ─────────────────────────────────────────────────────

    @api.model
    def _score_item(self, item, ctx, now, connection_set):
        """Calcule un score de pertinence pour un item du feed.

        score = (1 + engagement) × recency_decay × connection_factor × type_boost

        Signals :
        - Recency : décroissance HN-style avec demi-vie _HALF_LIFE_HOURS
        - Engagement : log-scale sur likes, comments, votes, views
        - Connexion : ×1.5 si l'auteur est une connexion acceptée
        - Type : boost urgence pour events proches et propositions qui ferment bientôt
        """
        # 1. Recency decay ────────────────────────────────────────────────────
        # Pour les events, timestamp = date_begin (futur) → age_hours = 0, decay = 1.0.
        # Le type_boost différencie les events proches (×2) vs. lointains (×1).
        ts = _parse_ts(item.get('timestamp', ''))
        if ts:
            age_hours = max(0.0, (now - ts).total_seconds() / 3600.0)
        else:
            age_hours = 8760.0  # fallback 1 an si pas de timestamp
        decay = 1.0 / (1.0 + age_hours / _HALF_LIFE_HOURS) ** _FEED_GRAVITY

        # 2. Engagement ───────────────────────────────────────────────────────
        likes = item.get('like_count') or 0
        comments = item.get('comment_count') or 0
        views = item.get('view_count') or 0
        votes = item.get('vote_count') or 0
        engagement = math.log1p(likes + comments * 2 + votes * 3 + views * 0.1)

        # 3. Connection affinity ───────────────────────────────────────────────
        author_id = item.get('author_id') or item.get('submitted_by_id')
        connection_factor = 1.5 if author_id in connection_set else 1.0

        # 4. Type-specific boosts ─────────────────────────────────────────────
        type_boost = 1.0
        itype = item.get('item_type')
        if itype == 'event':
            date_begin = _parse_ts(item.get('date_begin'))
            if date_begin:
                days_until = (date_begin - now).total_seconds() / 86400.0
                if 0.0 <= days_until <= 7.0:
                    type_boost = 2.0
                elif 0.0 <= days_until <= 30.0:
                    type_boost = 1.3
        elif itype == 'event_registration':
            # Les inscriptions de connexions sont toujours du contenu social pertinent.
            # Boost léger pour refléter l'urgence sociale (event à venir).
            event_date = _parse_ts(item.get('event_date_begin'))
            if event_date:
                days_until = (event_date - now).total_seconds() / 86400.0
                if 0.0 <= days_until <= 7.0:
                    type_boost = 1.8
                elif 0.0 <= days_until <= 30.0:
                    type_boost = 1.2
        elif itype == 'proposal':
            closes_at = _parse_ts(item.get('voting_closes_at'))
            if closes_at:
                hours_until = (closes_at - now).total_seconds() / 3600.0
                if 0.0 < hours_until <= 24.0:
                    type_boost = 2.0
                elif 0.0 < hours_until <= 72.0:
                    type_boost = 1.5
        elif itype == 'story':
            type_boost = 1.2

        # 5. Per-user preference boost (Feed v2) ──────────────────────────────
        # Multiplies the final score by whatever the user has configured
        # for this item type (1.0 default = no change). The boost_factor
        # is already clamped at write time, so we trust the value here.
        user_boost = (ctx.get('user_boosts') or {}).get(itype, 1.0)

        return (1.0 + engagement) * decay * connection_factor * type_boost * user_boost

    # ── Context helpers ───────────────────────────────────────────────────────

    @api.model
    def _feed_context(self):
        user = self.env.user
        blocked_ids = self.env['social_safety.block'].get_blocked_ids_for(user)
        connection_user_ids = self.env['club_social_profile.connection'].search([
            ('user_id', '=', user.id),
            ('state', '=', 'accepted'),
        ]).mapped('connected_user_id.id')
        member_group_ids = self.env['social_group.group'].search(
            [('member_ids', 'in', [user.id])]
        ).ids
        circle_ids = self.env['social_circles.circle'].search(
            [('member_ids', 'in', [user.id])]
        ).ids
        # Per-user type boosts (Feed v2). Sparse: only types the user
        # explicitly tweaked appear here. Missing types implicitly use 1.0.
        user_boosts = self.env['social_feed.user_preference'].sudo().boosts_for_user(user.id)
        return {
            'user': user,
            'blocked_ids': blocked_ids,
            'connection_user_ids': connection_user_ids,
            'member_group_ids': member_group_ids,
            'circle_ids': circle_ids,
            'user_boosts': user_boosts,
        }

    # ── Posts ─────────────────────────────────────────────────────────────────

    @api.model
    def _feed_posts(self, ctx, limit):
        user = ctx['user']

        # Delegate visibility rules to the single source of truth on the post model
        domain = self.env['social_base.post']._visibility_domain(
            user,
            connection_user_ids=ctx['connection_user_ids'],
            member_group_ids=ctx['member_group_ids'],
            blocked_user_ids=ctx['blocked_ids'],
        )

        posts = self.env['social_base.post'].search(domain, limit=limit)
        return [self._post_item(p) for p in posts]

    def _post_item(self, p):
        plain = re.sub(r'<[^>]+>', '', p.content or '')[:200].strip()
        return {
            'item_type': 'post',
            'id': p.id,
            'timestamp': p.create_date.isoformat() if p.create_date else '',
            'author_id': p.author_id.id,
            'author_name': p.author_id.name,
            'content_excerpt': plain or None,
            'visibility': p.visibility,
            'like_count': p.like_count,
            'comment_count': p.comment_count,
            'group_id': p.group_id.id if p.group_id else None,
            'group_name': p.group_id.name if p.group_id else None,
        }

    # ── Stories ───────────────────────────────────────────────────────────────

    @api.model
    def _feed_stories(self, ctx, limit):
        user = ctx['user']
        blocked_ids = ctx['blocked_ids']
        connection_user_ids = ctx['connection_user_ids']

        # Only stories from accepted connections (and yourself), still active
        author_ids = connection_user_ids + [user.id]
        domain = [
            ('state', '=', 'active'),
            ('author_id', 'in', author_ids),
        ]
        if blocked_ids:
            domain.append(('author_id', 'not in', blocked_ids))

        stories = self.env['social_story.story'].search(domain, limit=limit)
        return [self._story_item(s) for s in stories]

    def _story_item(self, s):
        return {
            'item_type': 'story',
            'id': s.id,
            'timestamp': s.create_date.isoformat() if s.create_date else '',
            'author_id': s.author_id.id,
            'author_name': s.author_id.name,
            'name': s.name,
            'expires_at': s.expires_at.isoformat() if s.expires_at else None,
            'view_count': s.view_count,
        }

    # ── Events ────────────────────────────────────────────────────────────────

    @api.model
    def _feed_events(self, ctx, limit):
        circle_ids = ctx['circle_ids']
        now = fields.Datetime.now()

        visibility_domain = [
            '|',
            ('social_visibility', '=', False),
            '|',
            ('social_visibility', '=', 'members'),
            ('allowed_circle_ids', 'in', circle_ids),
        ]
        domain = [('date_begin', '>=', now)] + visibility_domain
        events = self.env['event.event'].search(
            domain, limit=limit, order='date_begin asc'
        )
        if not events:
            return []

        # Batch-fetch attendee counts and connection attendee names (2 queries total)
        event_ids = events.ids
        all_regs = self.env['event.registration'].sudo().search([
            ('event_id', 'in', event_ids),
            ('state', '=', 'open'),
        ])
        attendee_counts = defaultdict(int)
        for reg in all_regs:
            attendee_counts[reg.event_id.id] += 1

        connection_user_ids = ctx['connection_user_ids']
        conn_names_by_event = defaultdict(list)
        if connection_user_ids:
            conn_partners = set(
                self.env['res.users'].browse(connection_user_ids).mapped('partner_id.id')
            )
            for reg in all_regs:
                if (reg.partner_id.id in conn_partners
                        and len(conn_names_by_event[reg.event_id.id]) < 3):
                    conn_names_by_event[reg.event_id.id].append(reg.partner_id.name)

        return [
            self._event_item(e, attendee_counts, conn_names_by_event)
            for e in events
        ]

    def _event_item(self, e, attendee_counts=None, conn_names_by_event=None):
        return {
            'item_type': 'event',
            'id': e.id,
            'timestamp': e.date_begin.isoformat() if e.date_begin else '',
            'name': e.name,
            'date_begin': e.date_begin.isoformat() if e.date_begin else None,
            'date_end': e.date_end.isoformat() if e.date_end else None,
            'organizer_name': e.organizer_user_id.name if e.organizer_user_id else None,
            'social_visibility': e.social_visibility or None,
            'attendee_count': (attendee_counts or {}).get(e.id, 0),
            'connection_attendee_names': list((conn_names_by_event or {}).get(e.id, [])),
        }

    # ── Event registrations (RSVP des connexions) ─────────────────────────────

    @api.model
    def _feed_event_registrations(self, ctx, limit):
        """Retourne les inscriptions d'événements des connexions de l'utilisateur.

        Seules les inscriptions confirmées (state='open') à des événements futurs
        par des connexions acceptées sont incluses. Les utilisateurs bloqués sont exclus.
        """
        connection_user_ids = ctx['connection_user_ids']
        if not connection_user_ids:
            return []

        blocked_ids = set(ctx['blocked_ids'])
        connection_users = self.env['res.users'].browse(connection_user_ids)

        # Mapping partner_id → user_id pour le champ author_id (scoring connexion)
        partner_to_user = {}
        conn_partner_ids = []
        for u in connection_users:
            if u.id not in blocked_ids:
                conn_partner_ids.append(u.partner_id.id)
                partner_to_user[u.partner_id.id] = u.id

        if not conn_partner_ids:
            return []

        now = fields.Datetime.now()
        regs = self.env['event.registration'].sudo().search([
            ('partner_id', 'in', conn_partner_ids),
            ('state', '=', 'open'),
            ('event_id.date_begin', '>=', now),
        ], limit=limit, order='create_date desc')

        return [self._event_registration_item(reg, partner_to_user) for reg in regs]

    def _event_registration_item(self, reg, partner_to_user=None):
        return {
            'item_type': 'event_registration',
            'id': reg.id,
            'timestamp': reg.create_date.isoformat() if reg.create_date else '',
            # author_id = user_id du membre inscrit (pour scoring connexion)
            'author_id': (partner_to_user or {}).get(reg.partner_id.id),
            'registrant_name': reg.partner_id.name,
            'registrant_partner_id': reg.partner_id.id,
            'event_id': reg.event_id.id,
            'event_name': reg.event_id.name,
            'event_date_begin': reg.event_id.date_begin.isoformat() if reg.event_id.date_begin else None,
            'event_date_end': reg.event_id.date_end.isoformat() if reg.event_id.date_end else None,
        }

    # ── Governance proposals ──────────────────────────────────────────────────

    @api.model
    def _feed_proposals(self, ctx, limit):
        proposals = self.env['social_governance.proposal'].search(
            [('state', '=', 'voting')], limit=limit
        )
        return [self._proposal_item(p) for p in proposals]

    def _proposal_item(self, p):
        return {
            'item_type': 'proposal',
            'id': p.id,
            'timestamp': (p.voting_opens_at or p.create_date or datetime.min).isoformat(),
            'title': p.name,
            'author_name': p.author_id.name if p.author_id else None,
            'voting_closes_at': p.voting_closes_at.isoformat() if p.voting_closes_at else None,
            'vote_count': p.vote_count,
        }

    # ── Gallery photos ────────────────────────────────────────────────────────

    @api.model
    def _feed_gallery(self, ctx, limit):
        blocked_ids = ctx['blocked_ids']
        domain = [
            ('state', '=', 'approved'),
            ('gallery_id.visibility', 'in', ['public', 'members']),
        ]
        if blocked_ids:
            domain += ['|',
                       ('submitted_by_id', '=', False),
                       ('submitted_by_id', 'not in', blocked_ids)]
        photos = self.env['social_gallery.photo'].search(
            domain, order='moderation_date desc, id desc', limit=limit
        )
        return [self._gallery_item(p) for p in photos]

    def _gallery_item(self, p):
        ts = p.moderation_date or p.create_date
        return {
            'item_type': 'gallery',
            'id': p.id,
            'timestamp': ts.isoformat() if ts else '',
            'gallery_id': p.gallery_id.id,
            'gallery_name': p.gallery_id.name,
            'photo_name': p.name or None,
            'submitted_by_id': p.submitted_by_id.id if p.submitted_by_id else None,
            'submitted_by_name': p.submitted_by_id.name if p.submitted_by_id else None,
        }
