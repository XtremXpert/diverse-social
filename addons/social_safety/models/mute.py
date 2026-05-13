from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class SocialMute(models.Model):
    _name = 'social_safety.mute'
    _description = 'User Mute'
    _order = 'create_date desc'

    muter_id = fields.Many2one(
        'res.users', required=True, index=True, ondelete='cascade',
        default=lambda self: self.env.user,
    )
    muted_id = fields.Many2one(
        'res.users', required=True, index=True, ondelete='cascade',
    )
    until = fields.Datetime(
        'Mute Until',
        help='Leave empty for permanent mute.',
    )
    is_active = fields.Boolean(compute='_compute_is_active', store=False)
    create_date = fields.Datetime('Muted On', readonly=True)

    _sql_constraints = [
        ('unique_mute', 'UNIQUE(muter_id, muted_id)', 'Already muted.'),
    ]

    @api.constrains('muter_id', 'muted_id')
    def _check_not_self(self):
        for rec in self:
            if rec.muter_id == rec.muted_id:
                raise ValidationError(_('You cannot mute yourself.'))

    @api.depends('until')
    def _compute_is_active(self):
        now = fields.Datetime.now()
        for rec in self:
            rec.is_active = not rec.until or rec.until > now

    @api.model
    def mute_user(self, muted_user, until=None):
        """Mute muted_user on behalf of the current user. Idempotent."""
        existing = self.search([
            ('muter_id', '=', self.env.user.id),
            ('muted_id', '=', muted_user.id),
        ], limit=1)
        if existing:
            if until:
                existing.write({'until': until})
            return existing
        return self.create({
            'muter_id': self.env.user.id,
            'muted_id': muted_user.id,
            'until': until,
        })

    @api.model
    def unmute_user(self, muted_user):
        self.search([
            ('muter_id', '=', self.env.user.id),
            ('muted_id', '=', muted_user.id),
        ]).unlink()

    @api.model
    def is_muted(self, muter_user, muted_user):
        """True if muter has an active mute on muted_user."""
        now = fields.Datetime.now()
        return bool(self.sudo().search([
            ('muter_id', '=', muter_user.id),
            ('muted_id', '=', muted_user.id),
            '|', ('until', '=', False), ('until', '>', now),
        ], limit=1))

    @api.model
    def cron_expire_mutes(self):
        expired = self.search([
            ('until', '!=', False),
            ('until', '<=', fields.Datetime.now()),
        ])
        count = len(expired)
        expired.unlink()
        return count
