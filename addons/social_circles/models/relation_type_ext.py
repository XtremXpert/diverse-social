from odoo import fields, models


class ResPartnerRelationType(models.Model):
    """Extend res.partner.relation.type with an optional link to a circle type.

    When a relation of this type is created, both partners are automatically
    added to their respective circle of the linked circle type.
    Leave blank to disable the automatic circle sync for this relation type.
    """
    _inherit = 'res.partner.relation.type'

    circle_type_id = fields.Many2one(
        'social_circles.circle_type',
        string='Auto-sync Circle Type',
        ondelete='set null',
        help='If set, creating a relation of this type automatically adds both '
             'members to their respective circle of this type.',
    )
