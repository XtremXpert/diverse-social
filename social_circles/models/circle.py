from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class SocialCircle(models.Model):
    _name = 'social_circles.circle'
    _description = 'Trust Circle'
    _order = 'sequence asc, id asc'

    profile_id = fields.Many2one(
        'club_social_profile.profile', required=True,
        ondelete='cascade', index=True,
    )

    # Type from the admin catalogue — mandatory, defines the canonical name
    type_id = fields.Many2one(
        'social_circles.circle_type', string='Circle Type',
        required=True, ondelete='restrict', index=True,
    )

    # Optional personal nickname; if blank, the type name is displayed
    name = fields.Char(
        string='Nickname (optional)',
        help='Leave blank to use the type name as-is.',
        translate=True,
    )

    # Computed label shown everywhere in the UI
    display_name = fields.Char(
        compute='_compute_display_name', store=True, string='Label',
    )

    description = fields.Text(translate=True)
    sequence = fields.Integer(default=10)
    color = fields.Integer(compute='_compute_color', store=True)

    member_ids = fields.Many2many(
        'res.users',
        'social_circles_member_rel',
        'circle_id', 'user_id',
        string='Members',
    )
    member_count = fields.Integer(compute='_compute_member_count', store=True)

    @api.depends('name', 'type_id', 'type_id.name')
    def _compute_display_name(self):
        for circle in self:
            circle.display_name = circle.name or (circle.type_id.name if circle.type_id else '')

    @api.depends('type_id', 'type_id.color')
    def _compute_color(self):
        for circle in self:
            # Inherit color from type unless overridden via a future field
            circle.color = circle.type_id.color if circle.type_id else 0

    @api.depends('member_ids')
    def _compute_member_count(self):
        for circle in self:
            circle.member_count = len(circle.member_ids)

    @api.constrains('profile_id', 'type_id')
    def _check_unique_type(self):
        for circle in self:
            if self.search_count([
                ('profile_id', '=', circle.profile_id.id),
                ('type_id', '=', circle.type_id.id),
                ('id', '!=', circle.id),
            ]):
                raise ValidationError(_(
                    'A circle of type "%(name)s" already exists for this profile.',
                    name=circle.type_id.name,
                ))

    def add_member(self, user):
        self.ensure_one()
        if user not in self.member_ids:
            self.sudo().write({'member_ids': [(4, user.id)]})

    def remove_member(self, user):
        self.ensure_one()
        self.sudo().write({'member_ids': [(3, user.id)]})

    def has_member(self, user):
        self.ensure_one()
        return user in self.member_ids
