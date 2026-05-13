import re
from datetime import datetime

from odoo import api, fields, models

DEFAULT_LIMIT = 20
MAX_LIMIT = 100
VALID_TYPES = frozenset({'post', 'story', 'event', 'proposal', 'gallery'})


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
            'proposal': self._feed_proposals,
            'gallery': self._feed_gallery,
        }

    @api.model
    def get_feed(self, limit=DEFAULT_LIMIT, offset=0, types=None):
        """Retourne le fil d'actualité de l'utilisateur courant.

        Items triés par timestamp DESC, avec respect de toutes les règles de
        visibilité (blocs, amis, cercles, groupes secrets, vie privée).
        """
        limit = min(int(limit), MAX_LIMIT)
        offset = int(offset)
        valid_types = self._get_feed_types()
        active_types = (
            [t for t in types if t in valid_types] if types else list(valid_types)
        )

        # Fetch a generous buffer from each type to cover the requested slice
        fetch_n = (limit + offset) * 2 + 20
        ctx = self._feed_context()

        items = []
        dispatch = self._get_feed_dispatch()
        for t in active_types:
            items.extend(dispatch[t](ctx, fetch_n))

        items.sort(key=lambda x: x['timestamp'], reverse=True)
        return {
            'items': items[offset: offset + limit],
            'has_more': len(items) > offset + limit,
        }

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
        return {
            'user': user,
            'blocked_ids': blocked_ids,
            'connection_user_ids': connection_user_ids,
            'member_group_ids': member_group_ids,
            'circle_ids': circle_ids,
        }

    # ── Posts ─────────────────────────────────────────────────────────────────

    @api.model
    def _feed_posts(self, ctx, limit):
        user = ctx['user']
        blocked_ids = ctx['blocked_ids']
        connection_user_ids = ctx['connection_user_ids']
        member_group_ids = ctx['member_group_ids']

        # visibility rules (OR'd together):
        #   public / members  → all social users
        #   friends           → author is a connection
        #   private           → only the author themselves
        # group_id set + group is secret → only group members see it
        visibility_domain = [
            '|', '|', '|',
            ('visibility', 'in', ['public', 'members']),
            '&', ('visibility', '=', 'friends'),
                 ('author_id', 'in', connection_user_ids + [user.id]),
            ('visibility', '=', 'private'), ('author_id', '=', user.id),
            '&', ('group_id', '!=', False),
                 ('group_id', 'in', member_group_ids),
        ]
        # For non-group posts, exclude posts whose group is secret and user isn't a member
        # This is already handled: secret group posts have group_id set, and we only include
        # group posts where group_id in member_group_ids.
        # Non-group posts (group_id=False) fall through to visibility check only.
        # So we need to also allow non-group posts:
        visibility_domain = [
            '|',
            ('group_id', '=', False),
            ('group_id', 'in', member_group_ids),
            '|', '|', '|',
            ('visibility', 'in', ['public', 'members']),
            '&', ('visibility', '=', 'friends'),
                 ('author_id', 'in', connection_user_ids + [user.id]),
            '&', ('visibility', '=', 'private'),
                 ('author_id', '=', user.id),
        ]

        domain = [('state', '=', 'published')] + visibility_domain
        if blocked_ids:
            domain.append(('author_id', 'not in', blocked_ids))

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
        user = ctx['user']
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
        return [self._event_item(e) for e in events]

    def _event_item(self, e):
        return {
            'item_type': 'event',
            'id': e.id,
            'timestamp': e.date_begin.isoformat() if e.date_begin else '',
            'name': e.name,
            'date_begin': e.date_begin.isoformat() if e.date_begin else None,
            'date_end': e.date_end.isoformat() if e.date_end else None,
            'organizer_name': e.organizer_user_id.name if e.organizer_user_id else None,
            'social_visibility': e.social_visibility or None,
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
