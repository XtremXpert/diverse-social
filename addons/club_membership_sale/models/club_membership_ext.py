from odoo import fields, models


class ClubMembership(models.Model):
    _inherit = 'club_membership.membership'

    sale_order_id = fields.Many2one(
        'sale.order', 'Commande',
        ondelete='set null', index=True, readonly=True,
    )
