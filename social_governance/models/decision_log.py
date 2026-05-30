from odoo import models, fields, api, _
from odoo.exceptions import UserError


class ModerationDecision(models.Model):
    _name = 'social_governance.decision_log'
    _description = 'Moderation Decision Log'
    _order = 'create_date desc'

    title = fields.Char('Decision', required=True)
    body = fields.Html('Details', required=True)
    moderator_id = fields.Many2one(
        'res.users', string='Moderator', required=True,
        default=lambda self: self.env.user, ondelete='restrict',
    )
    decision_date = fields.Date('Date', required=True, default=fields.Date.today)
    category = fields.Selection([
        ('ban', 'Member Ban'),
        ('warning', 'Warning Issued'),
        ('rule_change', 'Rule Change'),
        ('content_removal', 'Content Removal'),
        ('dispute', 'Dispute Resolution'),
        ('other', 'Other'),
    ], required=True, default='other')

    is_public = fields.Boolean(
        'Public',
        default=True,
        help='Publicly visible decisions build community trust. '
             'Set to private only for sensitive cases.',
    )
    related_proposal_id = fields.Many2one(
        'social_governance.proposal', string='Related Proposal', ondelete='set null',
    )

    @api.model
    def get_public_log(self, limit=50, offset=0):
        """Return public decisions for portal display."""
        return self.search_read(
            [('is_public', '=', True)],
            ['title', 'body', 'moderator_id', 'decision_date', 'category'],
            limit=limit,
            offset=offset,
            order='decision_date desc',
        )
