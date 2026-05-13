from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    membership_type_id = fields.Many2one(
        'club_membership.type',
        string="Type d'adhésion",
        help="Si renseigné, la vente de ce produit crée automatiquement une adhésion.",
        ondelete='set null',
    )
