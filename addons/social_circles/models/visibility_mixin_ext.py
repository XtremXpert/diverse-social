from odoo import fields, models


class ClubVisibilityMixinRelations(models.AbstractModel):
    """
    Extension of club.visibility.mixin to add 'relations' visibility level.
    This requires partner_multi_relation module for res.partner.relation.
    """
    _inherit = 'club.visibility.mixin'

    # Extend visibility selection to include 'relations'
    visibility = fields.Selection(
        selection_add=[('relations', 'Specific relations')],
        ondelete={'relations': 'set default'},
    )

    allowed_relation_type_ids = fields.Many2many(
        'res.partner.relation.type',
        string="Allowed relation types",
        help="Active only when visibility is 'Specific relations'. "
             "Visitor must have at least one confirmed relation of these types "
             "with the record owner.",
    )

    def _visibility_has_relation(self, owner_partner, visitor_partner):
        """Check for confirmed relation of allowed type between owner and visitor."""
        if not self.allowed_relation_type_ids:
            return False
        return bool(self.env['res.partner.relation'].sudo().search([
            '|',
            '&', ('left_partner_id', '=', owner_partner.id),
                 ('right_partner_id', '=', visitor_partner.id),
            '&', ('left_partner_id', '=', visitor_partner.id),
                 ('right_partner_id', '=', owner_partner.id),
            ('type_id', 'in', self.allowed_relation_type_ids.ids),
        ], limit=1))

    def _is_accessible_by(self, partner):
        """Extend to handle 'relations' visibility level."""
        self.ensure_one()

        # Handle 'relations' level
        if self.visibility == 'relations':
            owner = self._visibility_owner_partner()
            if not owner:
                return False
            return self._visibility_has_relation(owner, partner)

        # Delegate to parent for other levels
        return super()._is_accessible_by(partner)
