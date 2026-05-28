from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ClubMembershipType(models.Model):
    _inherit = 'club_membership.type'

    is_resident_default = fields.Boolean(
        string='Default for residency approval',
        help="When a moderator approves a residency, a membership of this type "
             "is created and activated. Exactly one active type should carry "
             "this flag per database.",
    )

    @api.constrains('is_resident_default', 'active')
    def _check_single_resident_default(self):
        for rec in self:
            if not rec.is_resident_default or not rec.active:
                continue
            others = self.search([
                ('is_resident_default', '=', True),
                ('active', '=', True),
                ('id', '!=', rec.id),
            ], limit=1)
            if others:
                raise ValidationError(_(
                    "Only one active membership type can be the default for "
                    "residency approval. Already set: %s"
                ) % others.name)
