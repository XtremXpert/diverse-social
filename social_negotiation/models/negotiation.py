from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError

_RESPONSE = [
    ('oui', 'Yes'),
    ('soft', 'Maybe / Soft'),
    ('non', 'No / Hard limit'),
    ('na', 'N/A'),
]

_CATEGORY = [
    ('hard_limit', 'Hard Limit'),
    ('soft_limit', 'Soft Limit'),
    ('desire', 'Desire'),
    ('safeguard', 'Safeguard / Aftercare'),
    ('other', 'Other'),
]


class SocialNegotiation(models.Model):
    _name = 'social_negotiation.negotiation'
    _description = 'Negotiation Document'
    _order = 'create_date desc'
    _inherit = ['mail.thread']

    initiator_id = fields.Many2one(
        'res.users', string='Initiator', required=True,
        default=lambda self: self.env.user, ondelete='restrict', index=True,
    )
    partner_id = fields.Many2one(
        'res.users', string='Partner', required=True,
        ondelete='restrict', index=True,
    )
    state = fields.Selection([
        ('draft', 'Draft'),
        ('shared', 'Shared — awaiting partner'),
        ('reviewing', 'Under Review'),
        ('active', 'Active'),
        ('archived', 'Archived'),
    ], default='draft', required=True, tracking=True)

    version = fields.Integer('Version', default=1, readonly=True)
    safe_word = fields.Char(
        'Safe Word',
        help='Agreed safe word. Stored encrypted-at-rest by the database; not displayed in lists.',
    )

    item_ids = fields.One2many('social_negotiation.item', 'negotiation_id', 'Items')

    initiator_signed_at = fields.Datetime('Initiator Signed At', readonly=True)
    partner_signed_at = fields.Datetime('Partner Signed At', readonly=True)
    archived_at = fields.Datetime('Archived At', readonly=True)

    is_fully_signed = fields.Boolean(compute='_compute_is_fully_signed')
    item_count = fields.Integer(compute='_compute_item_count')
    agreement_score = fields.Integer(
        compute='_compute_agreement_score',
        help='Percentage of items where both parties answered "Yes" or "Maybe".',
    )

    @api.depends('initiator_signed_at', 'partner_signed_at')
    def _compute_is_fully_signed(self):
        for neg in self:
            neg.is_fully_signed = bool(neg.initiator_signed_at and neg.partner_signed_at)

    @api.depends('item_ids')
    def _compute_item_count(self):
        for neg in self:
            neg.item_count = len(neg.item_ids)

    @api.depends('item_ids.initiator_response', 'item_ids.partner_response')
    def _compute_agreement_score(self):
        for neg in self:
            items = neg.item_ids.filtered(
                lambda i: i.initiator_response and i.partner_response
            )
            if not items:
                neg.agreement_score = 0
                continue
            compatible = items.filtered(
                lambda i: (i.initiator_response in ('oui', 'soft'))
                and (i.partner_response in ('oui', 'soft'))
            )
            neg.agreement_score = round(100 * len(compatible) / len(items))

    @api.constrains('initiator_id', 'partner_id')
    def _check_not_self(self):
        for neg in self:
            if neg.initiator_id == neg.partner_id:
                raise ValidationError(_('A negotiation requires two different people.'))

    # ── Workflow ──────────────────────────────────────────────────────────────

    def action_share(self):
        """Initiator shares the draft with the partner."""
        self.ensure_one()
        self._check_is_participant()
        if self.state != 'draft':
            raise UserError(_('Only a draft can be shared.'))
        self.write({'state': 'shared'})

    def action_start_review(self):
        """Partner opens the document for their side."""
        self.ensure_one()
        self._check_is_participant()
        if self.state != 'shared':
            raise UserError(_('Document must be in Shared state.'))
        self.write({'state': 'reviewing'})

    def action_sign(self):
        """Current user signs the document."""
        self.ensure_one()
        self._check_is_participant()
        if self.state not in ('reviewing', 'shared'):
            raise UserError(_('Document must be shared or under review to sign.'))
        now = fields.Datetime.now()
        if self.env.user == self.initiator_id:
            if self.initiator_signed_at:
                raise UserError(_('You have already signed this document.'))
            self.write({'initiator_signed_at': now})
        elif self.env.user == self.partner_id:
            if self.partner_signed_at:
                raise UserError(_('You have already signed this document.'))
            self.write({'partner_signed_at': now})
        if self.initiator_signed_at and self.partner_signed_at:
            self.write({'state': 'active'})

    def action_archive(self):
        """Archive — keeps the record for history."""
        self.ensure_one()
        self._check_is_participant()
        self._sudo_if_moderator().write({'state': 'archived', 'archived_at': fields.Datetime.now()})

    def action_new_version(self):
        """Create a new draft version based on this document."""
        self.ensure_one()
        self._check_is_participant()
        new_neg = self.copy({
            'state': 'draft',
            'version': self.version + 1,
            'initiator_signed_at': False,
            'partner_signed_at': False,
            'archived_at': False,
        })
        for item in self.item_ids:
            item.copy({'negotiation_id': new_neg.id})
        self.action_archive()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'social_negotiation.negotiation',
            'res_id': new_neg.id,
            'view_mode': 'form',
            'views': [(False, 'form')],  # requis par Odoo 20
        }

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _check_is_participant(self):
        if self.env.user not in (self.sudo().initiator_id, self.sudo().partner_id) \
                and not self.env.user.has_group('social_base.group_social_moderator'):
            raise UserError(_('Only the two parties or a moderator can act on this document.'))

    def _sudo_if_moderator(self):
        if self.env.user.has_group('social_base.group_social_moderator'):
            return self.sudo()
        return self


class NegotiationItem(models.Model):
    _name = 'social_negotiation.item'
    _description = 'Negotiation Item'
    _order = 'category asc, sequence asc, id asc'

    negotiation_id = fields.Many2one(
        'social_negotiation.negotiation', required=True, ondelete='cascade', index=True,
    )
    sequence = fields.Integer(default=10)
    category = fields.Selection(_CATEGORY, required=True, default='desire')
    text = fields.Char('Activity / Topic', required=True)
    initiator_response = fields.Selection(_RESPONSE, string='Initiator')
    partner_response = fields.Selection(_RESPONSE, string='Partner')
    note = fields.Text('Shared Note')

    is_compatible = fields.Boolean(compute='_compute_is_compatible')

    @api.depends('initiator_response', 'partner_response')
    def _compute_is_compatible(self):
        compatible_set = {'oui', 'soft'}
        for item in self:
            item.is_compatible = (
                item.initiator_response in compatible_set
                and item.partner_response in compatible_set
            )
