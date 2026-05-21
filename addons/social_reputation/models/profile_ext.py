from odoo import models, fields, api, _
from odoo.exceptions import UserError


class ClubSocialProfile(models.Model):
    _inherit = 'club_social_profile.profile'

    # ── Vouchings given (I am the sponsor) ───────────────────────────────────
    vouching_given_ids = fields.One2many(
        'social_reputation.vouching', 'sponsor_id',
        string='Vouchings Given',
        domain=[('state', '=', 'active')],
    )
    vouching_given_count = fields.Integer(
        compute='_compute_vouching_counts',
        compute_sudo=True,
    )

    # ── Vouchings received (I am the newcomer) ────────────────────────────────
    vouching_received_ids = fields.One2many(
        'social_reputation.vouching', 'newcomer_id',
        string='Vouchings Received',
        domain=[('state', '=', 'active')],
    )
    vouching_received_count = fields.Integer(
        compute='_compute_vouching_counts',
        compute_sudo=True,
    )
    is_vouched = fields.Boolean(
        compute='_compute_vouching_counts',
        compute_sudo=True,
        string='Has Sponsor',
        help='True if at least one active vouching exists for this profile.',
    )
    sponsor_ids = fields.Many2many(
        'res.users',
        compute='_compute_sponsor_ids',
        compute_sudo=True,
        string='Sponsors',
    )

    @api.depends('vouching_given_ids', 'vouching_received_ids',
                 'vouching_given_ids.state', 'vouching_received_ids.state')
    def _compute_vouching_counts(self):
        Vouching = self.env['social_reputation.vouching']
        for profile in self:
            given = Vouching.search_count([
                ('sponsor_id', '=', profile.user_id.id),
                ('state', '=', 'active'),
            ])
            received = Vouching.search_count([
                ('newcomer_id', '=', profile.user_id.id),
                ('state', '=', 'active'),
            ])
            profile.vouching_given_count = given
            profile.vouching_received_count = received
            profile.is_vouched = received > 0

    @api.depends('vouching_received_ids', 'vouching_received_ids.state')
    def _compute_sponsor_ids(self):
        Vouching = self.env['social_reputation.vouching']
        for profile in self:
            active = Vouching.search([
                ('newcomer_id', '=', profile.user_id.id),
                ('state', '=', 'active'),
            ])
            profile.sponsor_ids = active.mapped('sponsor_id')

    # ── Actions ───────────────────────────────────────────────────────────────

    def action_vouch(self, statement=None):
        """Current user vouches for this profile's owner."""
        self.ensure_one()
        if self.user_id == self.env.user:
            raise UserError(_('You cannot vouch for yourself.'))
        return self.env['social_reputation.vouching'].vouch_for(
            self.user_id, statement=statement
        )

    def action_withdraw_vouching(self, reason=None):
        """Current user withdraws their vouching for this profile's owner."""
        self.ensure_one()
        vouching = self.env['social_reputation.vouching'].search([
            ('sponsor_id', '=', self.env.user.id),
            ('newcomer_id', '=', self.user_id.id),
            ('state', '=', 'active'),
        ], limit=1)
        if not vouching:
            raise UserError(_('You have not vouched for this person.'))
        vouching.action_withdraw(reason=reason)

    def get_vouching_chain(self, depth=3):
        """
        Return the sponsorship chain up to `depth` levels.
        Result: list of sets of users at each level.
        Level 0 = direct sponsors of this profile.
        Level 1 = sponsors of those sponsors, etc.
        """
        self.ensure_one()
        Vouching = self.env['social_reputation.vouching'].sudo()
        visited = {self.user_id.id}
        chain = []
        current_ids = {self.user_id.id}

        for _ in range(depth):
            sponsors = Vouching.search([
                ('newcomer_id', 'in', list(current_ids)),
                ('state', '=', 'active'),
            ]).mapped('sponsor_id')
            new_sponsors = sponsors.filtered(lambda u: u.id not in visited)
            if not new_sponsors:
                break
            chain.append(new_sponsors)
            visited.update(new_sponsors.ids)
            current_ids = set(new_sponsors.ids)

        return chain
