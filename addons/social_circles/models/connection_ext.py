from odoo import models

# Name of the default circle into which new friends are auto-added.
# Users can rename or delete this circle at any time — it is never re-created.
_DEFAULT_CIRCLE_NAME = 'Connections'


class ClubSocialConnectionCircleExt(models.Model):
    """Extend connection acceptance to auto-add the new friend to the owner's
    default circle, if that circle already exists.

    This bridges the UX gap between Connections (bidirectional friendship)
    and Circles (named trust tiers): accepting a friend request now populates
    the circle automatically so visibility rules work without extra manual steps.

    The circle is NOT created if absent — only users who have chosen to organise
    their contacts into circles benefit from this behaviour.
    """
    _inherit = 'club_social_profile.connection'

    def action_accept(self):
        res = super().action_accept()
        # After acceptance, add the new friend to the acceptor's default circle
        # (if it exists) and to the requester's default circle (if it exists).
        self._sync_circles_on_accept()
        return res

    def _sync_circles_on_accept(self):
        """Add each party to the other's default circle, if that circle exists."""
        Profile = self.env['club_social_profile.profile']

        for conn in self:
            if conn.connection_type != 'friend':
                continue

            # Acceptor side: add requester (conn.user_id) to acceptor's circle
            acceptor_profile = Profile.sudo().search(
                [('user_id', '=', conn.connected_user_id.id)], limit=1
            )
            if acceptor_profile:
                circle = acceptor_profile.circle_ids.filtered(
                    lambda c: c.name == _DEFAULT_CIRCLE_NAME
                )[:1]
                if circle:
                    circle.add_member(conn.user_id)

            # Requester side: add acceptor (conn.connected_user_id) to requester's circle
            requester_profile = Profile.sudo().search(
                [('user_id', '=', conn.user_id.id)], limit=1
            )
            if requester_profile:
                circle = requester_profile.circle_ids.filtered(
                    lambda c: c.name == _DEFAULT_CIRCLE_NAME
                )[:1]
                if circle:
                    circle.add_member(conn.connected_user_id)
