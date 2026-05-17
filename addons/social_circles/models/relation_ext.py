from odoo import api, models


class ResPartnerRelation(models.Model):
    """Extend res.partner.relation to auto-sync circles when a relation is created.

    When a relation whose type has a circle_type_id is created, both partners
    are added to their respective circle of that type (creating the circle if absent).
    When the relation is deleted or archived, they are removed from that circle.
    """
    _inherit = 'res.partner.relation'

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._sync_circles('add')
        return records

    def unlink(self):
        # Collect sync info before deletion
        self._sync_circles('remove')
        return super().unlink()

    def write(self, vals):
        # Handle archiving (active=False) as a removal
        res = super().write(vals)
        if 'active' in vals:
            self._sync_circles('add' if vals['active'] else 'remove')
        return res

    def _sync_circles(self, action):
        """Add or remove both partners from their circle based on relation type.

        :param action: 'add' or 'remove'
        """
        Profile = self.env['club_social_profile.profile'].sudo()

        for rel in self:
            circle_type = rel.type_id.circle_type_id if rel.type_id else False
            if not circle_type:
                continue

            # Resolve both sides to res.users via their partner
            left_user = rel.left_partner_id.user_ids[:1]
            right_user = rel.right_partner_id.user_ids[:1]

            for user, other_user in [(left_user, right_user), (right_user, left_user)]:
                if not user or not other_user:
                    continue
                profile = Profile.search([('user_id', '=', user.id)], limit=1)
                if not profile:
                    continue

                if action == 'add':
                    # ensure_circle creates the circle if absent
                    profile.ensure_circle(circle_type).add_member(other_user)
                elif action == 'remove':
                    circle = profile.circle_ids.filtered(
                        lambda c: c.type_id.id == circle_type.id
                    )[:1]
                    if circle:
                        circle.remove_member(other_user)
