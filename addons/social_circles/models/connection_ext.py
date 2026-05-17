from odoo import models


class ClubSocialConnectionCircleExt(models.Model):
    """Extend connection acceptance to auto-add the new friend to each party's
    default circle (the circle_type with is_default=True).

    The default circle is provisioned automatically on profile creation
    (see profile_ext.py). Accepted friends land in that circle immediately,
    making circle-based visibility rules work out of the box.
    """
    _inherit = 'club_social_profile.connection'

    def action_accept(self):
        res = super().action_accept()
        self._sync_circles_on_accept()
        return res

    def _sync_circles_on_accept(self):
        """Add each party to the other's default circle type, creating it if absent."""
        Profile = self.env['club_social_profile.profile']
        default_type = self.env['social_circles.circle_type'].sudo().search(
            [('is_default', '=', True)], limit=1
        )
        if not default_type:
            return

        for conn in self:
            if conn.connection_type != 'friend':
                continue

            # Acceptor side: add requester into acceptor's default circle
            acceptor_profile = Profile.sudo().search(
                [('user_id', '=', conn.connected_user_id.id)], limit=1
            )
            if acceptor_profile:
                acceptor_profile.ensure_circle(default_type).add_member(conn.user_id)

            # Requester side: add acceptor into requester's default circle
            requester_profile = Profile.sudo().search(
                [('user_id', '=', conn.user_id.id)], limit=1
            )
            if requester_profile:
                requester_profile.ensure_circle(default_type).add_member(conn.connected_user_id)
