from odoo import fields, models


class ClubMembershipType(models.Model):
    _name = 'club_membership.type'
    _description = "Type d'adhésion"
    _order = 'sequence, name'

    name = fields.Char('Nom', required=True, translate=True)
    sequence = fields.Integer(default=10)
    description = fields.Text('Description', translate=True)
    fee = fields.Monetary('Cotisation annuelle', currency_field='currency_id')
    currency_id = fields.Many2one(
        'res.currency', default=lambda self: self.env.company.currency_id,
    )
    duration_months = fields.Integer(
        'Durée (mois)', default=12,
        help="Durée de validité de l'adhésion en mois. 0 = illimité (membre à vie).",
    )
    active = fields.Boolean(default=True)
    membership_count = fields.Integer(compute='_compute_membership_count')

    def _compute_membership_count(self):
        data = self.env['club_membership.membership'].read_group(
            [('membership_type_id', 'in', self.ids)],
            ['membership_type_id'],
            ['membership_type_id'],
        )
        counts = {d['membership_type_id'][0]: d['membership_type_id_count'] for d in data}
        for rec in self:
            rec.membership_count = counts.get(rec.id, 0)
