from odoo import models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    def _compute_display_name(self):
        super()._compute_display_name()
        for partner in self:
            users = partner.sudo().user_ids
            portal_users = users.filtered(lambda u: u.share and u.active)
            internal_users = users.filtered(lambda u: not u.share and u.active)
            # Uniquement pour les partenaires purement portail (pas d'utilisateur interne)
            if portal_users and not internal_users:
                partner.display_name = portal_users[:1].login
