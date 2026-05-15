from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError


class SocialVouching(models.Model):
    _name = 'social_reputation.vouching'
    _description = 'Community Vouching'
    _order = 'create_date desc'
    _inherit = ['mail.thread']

    sponsor_id = fields.Many2one(
        'res.users', string='Sponsor', required=True,
        default=lambda self: self.env.user,
        ondelete='restrict', index=True,
    )
    newcomer_id = fields.Many2one(
        'res.users', string='Newcomer', required=True,
        ondelete='restrict', index=True,
    )
    statement = fields.Text(
        'Statement',
        help='Why are you vouching for this person? Visible to the newcomer and moderators.',
    )
    state = fields.Selection([
        ('active', 'Active'),
        ('withdrawn', 'Withdrawn'),
    ], default='active', required=True, tracking=True)
    create_date = fields.Datetime('Vouched On', readonly=True)
    withdrawn_at = fields.Datetime('Withdrawn On', readonly=True)
    withdrawn_reason = fields.Text('Withdrawal Reason')

    _sql_constraints = [
        ('unique_vouching', 'UNIQUE(sponsor_id, newcomer_id)',
         'You have already vouched for this person.'),
    ]

    @api.constrains('sponsor_id', 'newcomer_id')
    def _check_not_self(self):
        for rec in self:
            if rec.sponsor_id == rec.newcomer_id:
                raise ValidationError(_('You cannot vouch for yourself.'))

    @api.constrains('sponsor_id', 'newcomer_id')
    def _check_no_circular(self):
        """Prevent A vouching B if B has already vouched A."""
        for rec in self:
            reverse = self.search([
                ('sponsor_id', '=', rec.newcomer_id.id),
                ('newcomer_id', '=', rec.sponsor_id.id),
                ('state', '=', 'active'),
            ], limit=1)
            if reverse:
                raise ValidationError(_(
                    '%(newcomer)s has already vouched for you. '
                    'Circular vouching is not allowed.',
                    newcomer=rec.newcomer_id.name,
                ))

    def action_withdraw(self, reason=None):
        self.ensure_one()
        if self.env.user != self.sponsor_id and \
                not self.env.user.has_group('social_base.group_social_moderator'):
            raise UserError(_('Only the sponsor or a moderator can withdraw a vouching.'))
        if self.state == 'withdrawn':
            raise UserError(_('This vouching is already withdrawn.'))
        if not reason and not self.withdrawn_reason:
            raise UserError(_('A reason is required to withdraw a vouching.'))
        rec = self.sudo() if self.env.user.has_group('social_base.group_social_moderator') else self
        rec.write({
            'state': 'withdrawn',
            'withdrawn_at': fields.Datetime.now(),
            'withdrawn_reason': reason or self.withdrawn_reason,
        })

    @api.model
    def vouch_for(self, newcomer_user, statement=None):
        """Create an active vouching. Raises if already exists (active or withdrawn)."""
        existing = self.search([
            ('sponsor_id', '=', self.env.user.id),
            ('newcomer_id', '=', newcomer_user.id),
        ], limit=1)
        if existing and existing.state == 'active':
            raise UserError(_('You have already vouched for %(name)s.', name=newcomer_user.name))
        if existing and existing.state == 'withdrawn':
            raise UserError(_(
                'You previously withdrew your vouching for %(name)s. '
                'Contact a moderator to reinstate it.',
                name=newcomer_user.name,
            ))
        return self.create({
            'sponsor_id': self.env.user.id,
            'newcomer_id': newcomer_user.id,
            'statement': statement,
        })
