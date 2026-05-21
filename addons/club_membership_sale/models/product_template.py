from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    membership_type_id = fields.Many2one(
        'club_membership.type',
        string="Membership type",
        help="If set, selling this product automatically creates a membership.",
        ondelete='set null',
    )
