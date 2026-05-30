import re

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class SocialPostCategory(models.Model):
    _name = 'social_post_categories.category'
    _description = 'Social post category'
    _order = 'sequence, name'

    name = fields.Char(required=True, translate=True)
    code = fields.Char(
        required=True, size=32, index=True,
        help="Stable identifier — used by the public API to set a category "
             "without depending on database-specific IDs. Lower-case ASCII.",
    )
    description = fields.Text(translate=True)
    color = fields.Char(
        size=7, default='#6c757d',
        help="Hex color (#RRGGBB) used by the UI badge.",
    )
    icon = fields.Char(
        size=64,
        help="FontAwesome icon class (e.g. fa-bullhorn) or emoji.",
    )
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    post_count = fields.Integer(compute='_compute_post_count')

    _unique_code = models.Constraint(
        'UNIQUE(code)',
        'Category code must be unique.',
    )

    @api.constrains('code')
    def _check_code_shape(self):
        for rec in self:
            if not rec.code:
                continue
            if not re.fullmatch(r'[a-z0-9_]+', rec.code):
                raise ValidationError(_(
                    "Category code must contain only lowercase letters, "
                    "digits and underscores. Got: %s"
                ) % rec.code)

    def _compute_post_count(self):
        data = self.env['social_base.post'].read_group(
            [('category_id', 'in', self.ids)],
            ['category_id'],
            ['category_id'],
        )
        counts = {d['category_id'][0]: d['category_id_count'] for d in data}
        for rec in self:
            rec.post_count = counts.get(rec.id, 0)
