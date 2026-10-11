from datetime import timedelta

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError


class ConsentRequest(models.Model):
    _name = 'social_consent.request'
    _description = 'Consent Request'
    _order = 'submitted_at desc, id desc'
    _inherit = ['mail.thread']

    gate_id = fields.Many2one(
        'social_consent.gate', required=True, ondelete='cascade', index=True,
    )
    profile_id = fields.Many2one(related='gate_id.profile_id', store=True)
    requester_id = fields.Many2one(
        'res.users', required=True, default=lambda self: self.env.user,
        ondelete='cascade', index=True,
    )
    state = fields.Selection([
        ('draft', 'Draft'),
        ('submitted', 'Submitted'),
        ('under_review', 'Under Review'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('withdrawn', 'Withdrawn'),
    ], default='draft', required=True, tracking=True)

    submitted_at = fields.Datetime(readonly=True)
    reviewed_at = fields.Datetime(readonly=True)
    reviewer_note = fields.Text('Note from owner')
    answer_ids = fields.One2many('social_consent.answer', 'request_id', 'Answers')

    can_review = fields.Boolean(compute='_compute_can_review',
                                help='True once the minimum delay has elapsed.')

    @api.depends('submitted_at', 'gate_id.min_delay_hours', 'state')
    def _compute_can_review(self):
        now = fields.Datetime.now()
        for req in self:
            if not req.submitted_at or req.state not in ('submitted', 'under_review'):
                req.can_review = False
            else:
                earliest = req.submitted_at + timedelta(hours=req.gate_id.min_delay_hours)
                req.can_review = now >= earliest

    # ── Visitor actions ───────────────────────────────────────────────────────

    def action_submit(self):
        self.ensure_one()
        if self.requester_id != self.env.user:
            raise UserError(_('You can only submit your own request.'))
        if self.state != 'draft':
            raise UserError(_('Only draft requests can be submitted.'))
        self._check_required_answers()
        self.write({'state': 'submitted', 'submitted_at': fields.Datetime.now()})
        self.gate_id.profile_id.sudo()._notify_consent_received(self)

    def action_withdraw(self):
        self.ensure_one()
        if self.requester_id != self.env.user:
            raise UserError(_('You can only withdraw your own request.'))
        if self.state not in ('draft', 'submitted', 'under_review'):
            raise UserError(_('This request cannot be withdrawn.'))
        self.write({'state': 'withdrawn'})

    # ── Owner actions ─────────────────────────────────────────────────────────

    def _sudo_if_moderator(self):
        if self.env.user.has_group('social_base.group_social_moderator'):
            return self.sudo()
        return self

    def action_mark_under_review(self):
        self.ensure_one()
        self._check_is_gate_owner()
        if self.state != 'submitted':
            raise UserError(_('Request must be in submitted state.'))
        self._sudo_if_moderator().write({'state': 'under_review'})

    def action_approve(self, note=None):
        self.ensure_one()
        self._check_is_gate_owner()
        if self.state not in ('submitted', 'under_review'):
            raise UserError(_('Request must be submitted or under review.'))
        if not self.sudo().can_review:
            raise UserError(_(
                'The minimum review delay of %(hours)d hour(s) has not elapsed yet.',
                hours=self.sudo().gate_id.min_delay_hours,
            ))
        self._sudo_if_moderator().write({
            'state': 'approved',
            'reviewed_at': fields.Datetime.now(),
            'reviewer_note': note or self.reviewer_note,
        })

    def action_reject(self, note=None):
        self.ensure_one()
        self._check_is_gate_owner()
        if self.state not in ('submitted', 'under_review'):
            raise UserError(_('Request must be submitted or under review.'))
        self._sudo_if_moderator().write({
            'state': 'rejected',
            'reviewed_at': fields.Datetime.now(),
            'reviewer_note': note or self.reviewer_note,
        })

    # ── Constraints ───────────────────────────────────────────────────────────

    @api.constrains('gate_id', 'requester_id')
    def _check_no_duplicate_active(self):
        for req in self:
            active_states = ('draft', 'submitted', 'under_review', 'approved')
            domain = [
                ('gate_id', '=', req.gate_id.id),
                ('requester_id', '=', req.requester_id.id),
                ('state', 'in', active_states),
                ('id', '!=', req.id),
            ]
            if self.search_count(domain):
                raise ValidationError(_(
                    'You already have an active request for this profile.',
                ))

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _check_is_gate_owner(self):
        owner_user = self.sudo().gate_id.profile_id.user_id
        if self.env.user != owner_user and not self.env.user.has_group('social_base.group_social_moderator'):
            raise UserError(_('Only the profile owner or a moderator can perform this action.'))

    def _check_required_answers(self):
        for item in self.gate_id.item_ids.filtered('required'):
            answer = self.answer_ids.filtered(lambda a: a.item_id == item)
            if not answer:
                raise ValidationError(_(
                    'You must answer all required items. Missing: %(item)s', item=item.text
                ))
            if item.item_type == 'check' and not answer.checked:
                raise ValidationError(_(
                    'You must tick: %(item)s', item=item.text
                ))
            if item.item_type == 'question' and not (answer.text or '').strip():
                raise ValidationError(_(
                    'Answer required for: %(item)s', item=item.text
                ))


class ConsentAnswer(models.Model):
    _name = 'social_consent.answer'
    _description = 'Consent Gate Answer'

    request_id = fields.Many2one(
        'social_consent.request', required=True, ondelete='cascade', index=True,
    )
    item_id = fields.Many2one(
        'social_consent.gate_item', required=True, ondelete='cascade',
    )
    item_type = fields.Selection(related='item_id.item_type')
    item_text = fields.Char(related='item_id.text')
    checked = fields.Boolean()
    text = fields.Text('Answer')

    _unique_answer = models.Constraint('UNIQUE(request_id, item_id)', 'Duplicate answer for the same item.')
