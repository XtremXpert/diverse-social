from odoo import fields, models


VISIBILITY_SELECTION = [
    ('public', 'Public'),
    ('members', 'Members only'),
    ('connections', 'Connections only'),
]


class ClubVisibilityMixin(models.AbstractModel):
    """
    Reusable mixin to control record visibility based on three levels:
    public / members / connections.

    Usage:
      1. Add '_inherit': ['club.visibility.mixin'] to your model.
      2. Override `_visibility_owner_partner()` to return the partner
         who "owns" the record (used for 'connections' level).
         Default: empty partner (connections level falls back to members).
      3. Optionally override `_visibility_is_member(partner)` if your
         definition of "member" differs from default (internal non-portal user).

    Note: 'relations' visibility level is provided by social_circles module
    which extends this mixin with partner_multi_relation support.
    """
    _name = 'club.visibility.mixin'
    _description = 'Visibility Mixin'

    visibility = fields.Selection(
        VISIBILITY_SELECTION,
        string="Visibility",
        default='members',
        required=True,
        help="Determines who can see this record.",
    )

    # ── Methods to override in subclasses ────────────────────────────────

    def _visibility_owner_partner(self):
        """
        Return the res.partner who owns this record.
        Required for 'connections' level.
        Return empty recordset to disable connections level.
        """
        self.ensure_one()
        return self.env['res.partner']

    def _visibility_is_member(self, partner):
        """
        Return True if `partner` is considered a club member.
        Default: any internal user (in base.group_user).
        Override to check a specific group.
        """
        return bool(partner.sudo().user_ids.filtered(lambda u: not u.share and u.active))

    # ── Private methods ──────────────────────────────────────────────────

    def _visibility_has_connection(self, owner_partner, visitor_partner):
        """Check for accepted connection between owner and visitor."""
        Connection = self.env.get('club_social_profile.connection')
        if Connection is None:
            return False
        return bool(Connection.sudo().search([
            '|',
            '&', ('user_id.partner_id', '=', owner_partner.id),
                 ('connected_user_id.partner_id', '=', visitor_partner.id),
            '&', ('user_id.partner_id', '=', visitor_partner.id),
                 ('connected_user_id.partner_id', '=', owner_partner.id),
            ('state', '=', 'accepted'),
        ], limit=1))

    # ── Public entry point ───────────────────────────────────────────────

    def _is_accessible_by(self, partner):
        """
        Return True if `partner` (res.partner) can access this record.
        """
        self.ensure_one()

        owner = self._visibility_owner_partner()

        # Owner always sees their own content
        if owner and owner == partner:
            return True

        # If visibility not set (records before installation), fall back to 'members'
        visibility = self.visibility or 'members'

        if visibility == 'public':
            return True

        if visibility == 'members':
            return self._visibility_is_member(partner)

        if visibility == 'connections':
            if not owner:
                # No owner → fall back to 'members' level
                return self._visibility_is_member(partner)
            return self._visibility_has_connection(owner, partner)

        # For extended visibility levels (e.g., 'relations' from social_circles)
        # subclasses should override this method
        return False
