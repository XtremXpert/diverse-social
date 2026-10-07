import hashlib
import hmac
import logging
from collections import defaultdict
from datetime import timedelta

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)


_TYPE_LABELS = {
    'connection_request':   ('connection request', 'connection requests'),
    'connection_accepted':  ('accepted connection', 'accepted connections'),
    'post_like':            ('reaction to your posts', 'reactions to your posts'),
    'post_comment':         ('comment on your posts', 'comments on your posts'),
    'comment_reply':        ('reply to your comments', 'replies to your comments'),
    'new_message':          ('private message', 'private messages'),
    'profile_visit':        ('profile visit', 'profile visits'),
    'event_registration':   ('event registration', 'event registrations'),
    'group_join_request':   ('group join request', 'group join requests'),
    'group_join_approved':  ('group approval', 'group approvals'),
    'proposal_voting':      ('proposal open for voting', 'proposals open for voting'),
    'story_new':            ('new story', 'new stories'),
    'gallery_photo_approved': ('approved photo', 'approved photos'),
    'gallery_photo_rejected': ('rejected photo', 'rejected photos'),
    'vouching_received':    ('vouch', 'vouches'),
    'vouching_withdrawn':   ('vouch withdrawal', 'vouch withdrawals'),
    'negotiation_shared':   ('shared negotiation', 'shared negotiations'),
    'negotiation_signed':   ('signed negotiation', 'signed negotiations'),
    'negotiation_active':   ('active negotiation', 'active negotiations'),
    'circle_added':         ('circle invitation', 'circle invitations'),
}


def _label(notif_type, count):
    """Human label for a notification type (singular vs plural)."""
    sing, plur = _TYPE_LABELS.get(notif_type, (notif_type, notif_type))
    return sing if count == 1 else plur


class NotificationDigestService(models.AbstractModel):
    """Reactivation digest service.

    Goal: ping members who have unread notifications and haven't visited
    the site in a few days. Sends at most one digest per user per
    configurable interval (default 7 days) regardless of pending count.
    Content groups actors per notification type — "Alice and 2 others
    sent you private messages" — so the email is informative without
    listing every line item.
    """
    _name = 'social_notifications.digest_service'
    _description = 'Reactivation digest service'

    # ── Configuration helpers ────────────────────────────────────────────────
    @api.model
    def _param(self, key, default):
        return self.env['ir.config_parameter'].sudo().get_str(key, default)

    @api.model
    def _int_param(self, key, default):
        try:
            return int(self._param(key, default))
        except (TypeError, ValueError):
            return int(default)

    # ── Last-login lookup ────────────────────────────────────────────────────
    @api.model
    def _last_login_dates(self, user_ids):
        """Return {user_id: last_login_datetime} for the given users.

        res.users.login_date is a non-stored related on res.users.log;
        SQL filtering doesn't work against it. One batched query against
        the underlying log table is faster than per-user lookups and lets
        us treat "never logged in" as "infinitely inactive" cleanly.
        """
        if not user_ids:
            return {}
        self.env.cr.execute(
            "SELECT create_uid, MAX(create_date) "
            "FROM res_users_log WHERE create_uid IN %s GROUP BY create_uid",
            (tuple(user_ids),),
        )
        return {uid: ts for uid, ts in self.env.cr.fetchall()}

    # ── Eligibility ──────────────────────────────────────────────────────────
    @api.model
    def _eligible_user_ids(self, now=None):
        """User ids that should receive a digest right now.

        Criteria :
            - has at least one unread notification
            - hasn't logged in within `inactivity_days` (default 3)
            - last digest >= `min_interval_days` ago (default 7)
            - profile.digest_email_enabled = True
            - has an email address
            - is a non-share active user with email
        """
        now = now or fields.Datetime.now()
        inactivity = self._int_param('social_notifications.digest_inactivity_days', 3)
        interval = self._int_param('social_notifications.digest_min_interval_days', 7)

        inactivity_cutoff = now - timedelta(days=inactivity)
        last_digest_cutoff = now - timedelta(days=interval)

        # Step 1: candidate users by activity + email + group membership.
        # Note: login_date is a related (non-stored) field on res.users.log,
        # so we can't compare it inside the SQL search. We resolve last-login
        # in a single batched query against res.users.log below.
        Users = self.env['res.users'].sudo()
        candidates = Users.search([
            ('active', '=', True),
            ('share', '=', False),
            ('email', '!=', False),
            '|', ('last_notification_digest_sent', '=', False),
                 ('last_notification_digest_sent', '<=', last_digest_cutoff),
            ('all_group_ids', 'in',
             [self.env.ref('social_base.group_social_user').id]),
        ])
        if not candidates:
            return []
        last_login_by_user = self._last_login_dates(candidates.ids)
        candidates = candidates.filtered(
            lambda u: (
                last_login_by_user.get(u.id) is None
                or last_login_by_user[u.id] <= inactivity_cutoff
            )
        )

        # Step 2: intersect with users having unread notifs + opt-in.
        Notification = self.env['club_social_profile.notification'].sudo()
        Profile = self.env['club_social_profile.profile'].sudo()
        unread_user_ids = set(Notification.search([
            ('user_id', 'in', candidates.ids),
            ('is_read', '=', False),
        ]).mapped('user_id.id'))

        opted_in_user_ids = set(Profile.search([
            ('user_id', 'in', list(unread_user_ids)),
            ('digest_email_enabled', '=', True),
        ]).mapped('user_id.id'))

        return list(opted_in_user_ids)

    # ── Summary ──────────────────────────────────────────────────────────────
    @api.model
    def _summary_for_user(self, user, name_cap=3):
        """Build a per-user summary of unread notifications.

        Returns a list of dicts, one per (type, actor-group), sorted by
        recency. Each dict carries:
            type, count, label, sample_names (up to `name_cap`),
            extra_count (rest beyond name_cap), latest_url
        """
        Notification = self.env['club_social_profile.notification'].sudo()
        notifs = Notification.search([
            ('user_id', '=', user.id),
            ('is_read', '=', False),
        ], order='create_date desc')

        if not notifs:
            return []

        # Group by type, collect actor names (preferring stealth_name).
        groups = defaultdict(lambda: {
            'count': 0, 'actor_names': [], 'actor_ids_seen': set(),
            'latest_url': '', 'type': '',
        })
        Profile = self.env['club_social_profile.profile'].sudo()
        for n in notifs:
            key = n.type or 'other'
            g = groups[key]
            g['type'] = key
            g['count'] += 1
            if not g['latest_url'] and n.url:
                g['latest_url'] = n.url

            actor = n.actor_id
            if actor and actor.id not in g['actor_ids_seen']:
                g['actor_ids_seen'].add(actor.id)
                # Privacy-preserving display: stealth_name on the actor's
                # profile takes precedence over their real name.
                g['actor_names'].append(Profile._display_name_for_user(actor))

        out = []
        for g in groups.values():
            names = g['actor_names']
            sample = names[:name_cap]
            extra = max(0, len(names) - name_cap)
            out.append({
                'type': g['type'],
                'count': g['count'],
                'label': _label(g['type'], g['count']),
                'sample_names': sample,
                'extra_count': extra,
                'latest_url': g['latest_url'],
            })
        # Surface the largest groups first — best engagement signal.
        out.sort(key=lambda x: x['count'], reverse=True)
        return out

    # ── HMAC token for unsubscribe ───────────────────────────────────────────
    @api.model
    def _digest_secret(self):
        secret = self.env['ir.config_parameter'].sudo().get_str('database.secret', '')
        return (secret or 'social_notifications-fallback').encode('utf-8')

    @api.model
    def _unsubscribe_token(self, user_id):
        """One-way HMAC token for the unsubscribe link.

        The token is deterministic per user (no expiry needed — clicking
        is always valid), bound to the DB's secret so a leaked URL from
        one deployment can't be used on another.
        """
        payload = f'digest-unsubscribe:{user_id}'.encode('utf-8')
        return hmac.new(self._digest_secret(), payload, hashlib.sha256).hexdigest()

    @api.model
    def _verify_unsubscribe_token(self, user_id, token):
        expected = self._unsubscribe_token(user_id)
        return hmac.compare_digest(expected, token or '')

    # ── Send ─────────────────────────────────────────────────────────────────
    @api.model
    def _send_digest(self, user, summary):
        if not user.email or not summary:
            return False
        total = sum(g['count'] for g in summary)
        subject = self._param(
            'social_notifications.digest_subject',
            _('You have %(count)d pending notifications'),
        )
        # Allow %(count)d in the configured subject.
        try:
            subject = subject % {'count': total}
        except (KeyError, TypeError, ValueError):
            pass

        from_email = self._param('social_notifications.digest_from', '')
        if not from_email:
            from_email = self.env['ir.config_parameter'].sudo().get_str(
                'mail.default.from', 'noreply@example.com',
            )

        base_url = self.env['ir.config_parameter'].sudo().get_str('web.base.url', '')
        unsub_token = self._unsubscribe_token(user.id)
        unsubscribe_url = f'{base_url}/notifications/digest/unsubscribe/{user.id}/{unsub_token}'

        body_html = self.env['ir.qweb']._render(
            'social_notifications.email_notification_digest',
            {
                'user': user,
                'summary': summary,
                'total': total,
                'base_url': base_url,
                'unsubscribe_url': unsubscribe_url,
            },
        )

        self.env['mail.mail'].sudo().create({
            'subject': subject,
            'email_from': from_email,
            'email_to': user.email,
            'body_html': body_html,
            'auto_delete': True,
        }).send()
        user.sudo().last_notification_digest_sent = fields.Datetime.now()
        return True

    # ── Cron entry point ─────────────────────────────────────────────────────
    @api.model
    def cron_send_reactivation_digests(self):
        user_ids = self._eligible_user_ids()
        if not user_ids:
            return
        _logger.info('social_notifications: sending digests to %d user(s)', len(user_ids))
        sent = 0
        for user in self.env['res.users'].sudo().browse(user_ids):
            try:
                summary = self._summary_for_user(user)
                if summary and self._send_digest(user, summary):
                    sent += 1
            except Exception:
                _logger.exception('digest failed for user %s', user.id)
        _logger.info('social_notifications: sent %d digest(s)', sent)
        return sent
