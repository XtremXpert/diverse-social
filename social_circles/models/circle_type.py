from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class SocialCircleType(models.Model):
    """Admin-managed catalogue of circle types.

    Members cannot create or edit types — they can only choose from this list
    when creating a circle. Each circle instance may optionally add a personal
    nickname on top of the type name.
    """
    _name = 'social_circles.circle_type'
    _description = 'Circle Type'
    _order = 'sequence asc, id asc'

    name = fields.Char(required=True, translate=True)
    description = fields.Text(translate=True)
    sequence = fields.Integer(default=10)
    color = fields.Integer(default=0, string='Default Color')
    active = fields.Boolean(default=True)

    is_default = fields.Boolean(
        string='Default for new connections',
        default=False,
        help='If set, new profiles automatically get a circle of this type, '
             'and accepted friend connections are added to it.',
    )

    circle_count = fields.Integer(compute='_compute_circle_count', string='Circles')

    def _compute_circle_count(self):
        for t in self:
            t.circle_count = self.env['social_circles.circle'].sudo().search_count(
                [('type_id', '=', t.id)]
            )

    @api.constrains('is_default')
    def _check_single_default(self):
        for rec in self:
            if rec.is_default and self.search_count([
                ('is_default', '=', True),
                ('id', '!=', rec.id),
            ]):
                raise ValidationError(_(
                    'Only one circle type can be the default for new connections.'
                ))
