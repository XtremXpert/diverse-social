from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class ConsentGate(models.Model):
    _name = 'social_consent.gate'
    _description = 'Consent Gate'
    _rec_name = 'profile_id'

    profile_id = fields.Many2one(
        'club_social_profile.profile', required=True,
        ondelete='cascade', index=True,
    )
    is_active = fields.Boolean('Active', default=True)
    intro_text = fields.Text(
        'Introduction',
        help='Shown to the visitor before they fill in the gate.',
    )
    min_delay_hours = fields.Integer(
        'Minimum Review Delay (hours)', default=24,
        help='Owner cannot approve sooner than this after submission.',
    )
    require_all_checks = fields.Boolean(
        'Require all acknowledgements', default=True,
        help='All checkbox items must be ticked before submitting.',
    )
    item_ids = fields.One2many('social_consent.gate_item', 'gate_id', 'Items')
    request_ids = fields.One2many('social_consent.request', 'gate_id', 'Requests')
    pending_count = fields.Integer(compute='_compute_pending_count')

    @api.depends('request_ids.state')
    def _compute_pending_count(self):
        for gate in self:
            gate.pending_count = self.env['social_consent.request'].search_count([
                ('gate_id', '=', gate.id),
                ('state', 'in', ('submitted', 'under_review')),
            ])

    @api.constrains('profile_id')
    def _check_unique_gate(self):
        for gate in self:
            if self.search_count([('profile_id', '=', gate.profile_id.id), ('id', '!=', gate.id)]):
                raise ValidationError(_('A consent gate already exists for this profile.'))


class ConsentGateItem(models.Model):
    _name = 'social_consent.gate_item'
    _description = 'Consent Gate Item'
    _order = 'sequence asc, id asc'

    gate_id = fields.Many2one('social_consent.gate', required=True, ondelete='cascade')
    sequence = fields.Integer(default=10)
    item_type = fields.Selection([
        ('check', 'Acknowledgement'),
        ('question', 'Open Question'),
    ], required=True, default='check')
    text = fields.Char('Label / Question', required=True, translate=True)
    required = fields.Boolean(default=True)
    hint = fields.Char(
        'Hint',
        help='Optional guidance shown below the item.',
    )
