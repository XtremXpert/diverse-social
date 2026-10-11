from odoo import models, fields, api, _


class ClubSocialProfile(models.Model):
    _inherit = 'club_social_profile.profile'

    consent_gate_id = fields.Many2one(
        'social_consent.gate',
        compute='_compute_consent_gate_id',
        store=False,
        string='Consent Gate',
    )
    consent_required = fields.Boolean(
        compute='_compute_consent_gate_id',
        store=False,
        string='Consent Gate Active',
    )

    @api.depends('user_id')
    def _compute_consent_gate_id(self):
        gate_map = {}
        if self.ids:
            gates = self.env['social_consent.gate'].search([
                ('profile_id', 'in', self.ids),
                ('is_active', '=', True),
            ])
            gate_map = {g.profile_id.id: g for g in gates}
        for profile in self:
            gate = gate_map.get(profile.id)
            profile.consent_gate_id = gate
            profile.consent_required = bool(gate)

    def _notify_consent_received(self, request):
        """Hook — leaf modules or notification modules can override this."""
        pass

    def get_consent_status_for(self, requester_user):
        """Return the consent request state for requester_user, or False if none."""
        self.ensure_one()
        if not self.consent_gate_id:
            return False
        req = self.env['social_consent.request'].search([
            ('gate_id', '=', self.consent_gate_id.id),
            ('requester_id', '=', requester_user.id),
            ('state', 'in', ('submitted', 'under_review', 'approved')),
        ], limit=1, order='id desc')
        return req.state if req else 'none'
