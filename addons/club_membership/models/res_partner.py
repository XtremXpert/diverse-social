from odoo import fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    membership_ids = fields.One2many(
        'club_membership.membership', 'partner_id', 'Memberships',
    )
    current_membership_id = fields.Many2one(
        'club_membership.membership',
        compute='_compute_current_membership',
        string='Current membership',
        store=False,
    )
    member_state = fields.Selection([
        ('none', 'Not a member'),
        ('pending', 'Pending'),
        ('active', 'Active member'),
        ('expired', 'Expired'),
        ('suspended', 'Suspended'),
        ('cancelled', 'Cancelled'),
    ], compute='_compute_current_membership', string='Membership status', store=False)

    def _compute_current_membership(self):
        Membership = self.env['club_membership.membership']
        priority = {'active': 0, 'pending': 1, 'suspended': 2, 'expired': 3, 'cancelled': 4}
        for partner in self:
            memberships = Membership.search([('partner_id', '=', partner.id)])
            if not memberships:
                partner.current_membership_id = False
                partner.member_state = 'none'
                continue
            best = min(memberships, key=lambda m: priority.get(m.state, 99))
            partner.current_membership_id = best
            partner.member_state = best.state
