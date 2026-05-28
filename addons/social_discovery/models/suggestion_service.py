from odoo import api, models

# Tuning constants — see _score_profile().
_CANDIDATE_CAP = 100
_DEFAULT_LIMIT = 6
_CITY_BONUS = 20
_FRIEND_BONUS_PER = 5
_FRIEND_BONUS_MAX = 25
_BDSM_WEIGHT = 0.5


class SuggestionService(models.AbstractModel):
    """Ranks candidate profiles to show on a member's dashboard.

    AbstractModel — no table, uses the env of the calling user. Filters
    blocks and consent gates at runtime (modules may be uninstalled).

    Scoring is intentionally simple: BDSM compatibility ×0.5, +20 for a
    same-city match, +5 per mutual friend capped at +25. The cap on
    candidates (_CANDIDATE_CAP) keeps the per-dashboard cost bounded.
    """
    _name = 'social_discovery.suggestion_service'
    _description = 'Profile suggestion service'

    @api.model
    def get_suggestions(self, user=None, limit=_DEFAULT_LIMIT):
        """Return a list of dicts: [{'profile': recordset, 'score': int}, ...].

        Empty list when the viewer isn't eligible (no profile, onboarding
        incomplete) — by design, suggestions only appear once you've done
        the work of setting up your own profile.
        """
        user = user or self.env.user
        if not user.has_group('social_base.group_social_user'):
            return []

        Profile = self.env['club_social_profile.profile'].sudo()
        my_profile = Profile.search([('user_id', '=', user.id)], limit=1)
        if not my_profile or not my_profile.onboarding_done:
            # Asymmetric opt-in: the *viewer* must have finished onboarding.
            # Pushes nudge to complete profile before getting algorithmic feed.
            return []

        # ── Exclusions ────────────────────────────────────────────────────────
        # Already-connected users (pending or accepted) — rejected ones too:
        # not great UX to keep pushing someone who turned a request down.
        existing_conn_user_ids = self._connected_user_ids(user)

        # Blocks (bidirectional) — runtime check.
        blocked_ids = set()
        if 'social_safety.block' in self.env:
            blocked_ids = self.env['social_safety.block'].get_blocked_ids_for(user)

        excluded_user_ids = existing_conn_user_ids | blocked_ids | {user.id}

        # ── Candidate pool ────────────────────────────────────────────────────
        group_social_user = self.env.ref('social_base.group_social_user')
        candidates = Profile.search([
            ('user_id', 'not in', list(excluded_user_ids)),
            ('user_id.active', '=', True),
            ('user_id.all_group_ids', 'in', [group_social_user.id]),
            ('visibility', '=', 'members'),
            ('onboarding_done', '=', True),
        ], limit=_CANDIDATE_CAP)

        if not candidates:
            return []

        # Filter consent gates — runtime check.
        if 'social_consent.gate' in self.env:
            candidates = self._filter_consent_reachable(candidates, user)

        if not candidates:
            return []

        # ── Batched mutual-friend counts ──────────────────────────────────────
        # One SQL query for all candidates instead of one per profile.
        mutual_counts = self._mutual_friend_counts(user, candidates.mapped('user_id').ids)

        # Prefetch BDSM kinks if the module is installed, to warm the cache
        # before per-candidate compute_compatibility() runs.
        has_bdsm = 'bdsm_role' in Profile._fields
        if has_bdsm:
            candidates.mapped('kink_level_ids')
            my_profile.mapped('kink_level_ids')

        # ── Score and rank ────────────────────────────────────────────────────
        scored = []
        for candidate in candidates:
            score = self._score_profile(
                my_profile, candidate,
                mutual_count=mutual_counts.get(candidate.user_id.id, 0),
                has_bdsm=has_bdsm,
            )
            scored.append((score, candidate.id))

        scored.sort(key=lambda x: x[0], reverse=True)
        top = scored[:limit]
        return [
            {'profile': Profile.browse(cid), 'score': score}
            for score, cid in top
        ]

    # ── Helpers ──────────────────────────────────────────────────────────────

    @api.model
    def _connected_user_ids(self, user):
        """All user ids the viewer already has a connection with, regardless of state."""
        rows = self.env['club_social_profile.connection'].sudo().search([
            '|',
            ('user_id', '=', user.id),
            ('connected_user_id', '=', user.id),
        ])
        ids = set()
        for row in rows:
            ids.add(row.user_id.id)
            ids.add(row.connected_user_id.id)
        ids.discard(user.id)
        return ids

    @api.model
    def _mutual_friend_counts(self, viewer, candidate_user_ids):
        """Return {candidate_user_id: count_of_mutual_accepted_connections}.

        A single SQL query over club_social_profile_connection — cheaper than
        a Python loop calling search_count() per candidate.
        """
        if not candidate_user_ids:
            return {}
        # Friends of the viewer (accepted in either direction).
        Connection = self.env['club_social_profile.connection'].sudo()
        my_friends_rows = Connection.search([
            ('state', '=', 'accepted'),
            '|',
            ('user_id', '=', viewer.id),
            ('connected_user_id', '=', viewer.id),
        ])
        my_friend_ids = set()
        for row in my_friends_rows:
            other = row.connected_user_id.id if row.user_id.id == viewer.id else row.user_id.id
            my_friend_ids.add(other)
        if not my_friend_ids:
            return {}

        # For each candidate, count of (candidate ↔ my_friend) accepted rows.
        # Single search on connection table, group counts in Python from the
        # returned rowset — beats N searches.
        cand_friend_rows = Connection.search([
            ('state', '=', 'accepted'),
            '|',
            '&', ('user_id', 'in', list(candidate_user_ids)),
                 ('connected_user_id', 'in', list(my_friend_ids)),
            '&', ('connected_user_id', 'in', list(candidate_user_ids)),
                 ('user_id', 'in', list(my_friend_ids)),
        ])
        counts = {}
        for row in cand_friend_rows:
            uid = row.user_id.id if row.user_id.id in candidate_user_ids else row.connected_user_id.id
            counts[uid] = counts.get(uid, 0) + 1
        return counts

    @api.model
    def _filter_consent_reachable(self, profiles, user):
        """Exclude profiles whose active consent gate hasn't been approved for `user`."""
        Gate = self.env['social_consent.gate'].sudo()
        Req = self.env['social_consent.request'].sudo()
        keep = []
        for p in profiles:
            gate = Gate.search([('profile_id', '=', p.id), ('is_active', '=', True)], limit=1)
            if not gate:
                keep.append(p.id)
                continue
            approved = Req.search_count([
                ('gate_id', '=', gate.id),
                ('requester_id', '=', user.id),
                ('state', '=', 'approved'),
            ])
            if approved:
                keep.append(p.id)
        return self.env['club_social_profile.profile'].sudo().browse(keep)

    @api.model
    def _score_profile(self, my_profile, candidate, mutual_count=0, has_bdsm=False):
        """Score = BDSM_compat×0.5 + city_bonus + mutual_friends_bonus.

        Range: roughly 0–95 when BDSM is installed (50×0.5 baseline + bonuses),
        0–45 otherwise. Used only for ranking — exposed as a 0–100 badge.
        """
        score = 0

        if has_bdsm:
            try:
                compat = my_profile.compute_compatibility(candidate)
                score += compat['score'] * _BDSM_WEIGHT
            except Exception:
                pass

        if my_profile.city and candidate.city and \
                my_profile.city.strip().lower() == candidate.city.strip().lower():
            score += _CITY_BONUS

        score += min(mutual_count * _FRIEND_BONUS_PER, _FRIEND_BONUS_MAX)

        return round(score)
