from odoo import fields, models


class ClubMembershipType(models.Model):
    _name = 'club_membership.type'
    _description = "Membership type"
    _order = 'sequence, name'

    name = fields.Char('Name', required=True, translate=True)
    sequence = fields.Integer(default=10)
    description = fields.Text('Description', translate=True)
    fee = fields.Monetary('Annual fee', currency_field='currency_id')
    currency_id = fields.Many2one(
        'res.currency', default=lambda self: self.env.company.currency_id,
    )
    duration_months = fields.Integer(
        'Duration (months)', default=12,
        help="Membership validity in months. 0 = unlimited (lifetime member).",
    )
    active = fields.Boolean(default=True)
    membership_count = fields.Integer(compute='_compute_membership_count')

    def _compute_membership_count(self):
        # Odoo 19 : read_group → _read_group (groupby/aggregates, tuples).
        data = self.env['club_membership.membership']._read_group(
            [('membership_type_id', 'in', self.ids)],
            groupby=['membership_type_id'],
            aggregates=['__count'],
        )
        counts = {mtype.id: count for mtype, count in data}
        for rec in self:
            rec.membership_count = counts.get(rec.id, 0)
