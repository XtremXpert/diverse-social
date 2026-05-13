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
    name = fields.Char(required=True, translate=True)
    description = fields.Text(translate=True)
    sequence = fields.Integer(default=10)
    color = fields.Integer(default=0)

    member_ids = fields.Many2many(
        'res.users',
        'social_circles_member_rel',
        'circle_id', 'user_id',
        string='Members',
    )
    member_count = fields.Integer(compute='_compute_member_count', store=True)

    @api.depends('member_ids')
    def _compute_member_count(self):
        for circle in self:
            circle.member_count = len(circle.member_ids)

    @api.constrains('profile_id', 'name')
    def _check_unique_name(self):
        for circle in self:
            if self.search_count([
                ('profile_id', '=', circle.profile_id.id),
                ('name', '=', circle.name),
                ('id', '!=', circle.id),
            ]):
                raise ValidationError(_(
                    'A circle named "%(name)s" already exists for this profile.',
                    name=circle.name,
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
