from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError


class SocialBlock(models.Model):
    _name = 'social_safety.block'
    _description = 'User Block'
    _order = 'create_date desc'

    blocker_id = fields.Many2one(
        'res.users', required=True, index=True, ondelete='cascade',
        default=lambda self: self.env.user,
    )
    blocked_id = fields.Many2one(
        'res.users', required=True, index=True, ondelete='cascade',
    )
    reason = fields.Text('Private Note')
    create_date = fields.Datetime('Blocked On', readonly=True)

    _sql_constraints = [
        ('unique_block', 'UNIQUE(blocker_id, blocked_id)', 'Already blocked.'),
    ]

    @api.constrains('blocker_id', 'blocked_id')
    def _check_not_self(self):
        for rec in self:
            if rec.blocker_id == rec.blocked_id:
                raise ValidationError(_('You cannot block yourself.'))

    @api.model
    def block_user(self, blocked_user, reason=None):
        """Block blocked_user on behalf of the current user. Idempotent."""
        existing = self.search([
            ('blocker_id', '=', self.env.user.id),
            ('blocked_id', '=', blocked_user.id),
        ], limit=1)
        if existing:
            return existing
        return self.create({
            'blocker_id': self.env.user.id,
            'blocked_id': blocked_user.id,
            'reason': reason,
        })

    @api.model
    def unblock_user(self, blocked_user):
        """Remove block. No-op if not blocked."""
        self.search([
            ('blocker_id', '=', self.env.user.id),
            ('blocked_id', '=', blocked_user.id),
        ]).unlink()

    @api.model
    def is_blocked(self, user_a, user_b):
        """True if either user has blocked the other."""
        return bool(self.sudo().search([
            '|',
            '&', ('blocker_id', '=', user_a.id), ('blocked_id', '=', user_b.id),
            '&', ('blocker_id', '=', user_b.id), ('blocked_id', '=', user_a.id),
        ], limit=1))

    @api.model
    def get_blocked_ids_for(self, user):
        """Return IDs of users blocked by OR blocking user (both directions)."""
        records = self.sudo().search([
            '|',
            ('blocker_id', '=', user.id),
            ('blocked_id', '=', user.id),
        ])
        ids = set()
        for r in records:
            ids.add(r.blocker_id.id)
            ids.add(r.blocked_id.id)
        ids.discard(user.id)
        return list(ids)
