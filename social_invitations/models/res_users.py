from odoo import api, models


class ResUsers(models.Model):
    _inherit = "res.users"

    @api.model_create_multi
    def create(self, vals_list):
        users = super().create(vals_list)
        # Matérialise les invitations groupe/cercle en attente pour ces courriels.
        self.env["social_invitations.pending"].sudo()._consume_for_users(users)
        return users
