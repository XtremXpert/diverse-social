import logging

from odoo import models

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    _inherit = 'account.move'

    def _compute_payment_state(self):
        old_states = {r.id: r.payment_state for r in self}
        super()._compute_payment_state()
        for move in self:
            if (
                move.move_type == 'out_invoice'
                and old_states.get(move.id) != 'paid'
                and move.payment_state == 'paid'
            ):
                move._activate_memberships_on_payment()

    def _activate_memberships_on_payment(self):
        """Activate pending memberships linked to this invoice or to its order."""
        self.ensure_one()
        Membership = self.env['club_membership.membership'].sudo()

        # Lookup via sale_order_id (orders linked to this invoice)
        sale_orders = self.env['sale.order'].sudo().search([
            ('invoice_ids', 'in', [self.id])
        ])
        pending = Membership.search([
            '|',
            ('sale_order_id', 'in', sale_orders.ids),
            ('invoice_id', '=', self.id),
            ('state', '=', 'pending'),
        ])

        for membership in pending:
            try:
                membership.invoice_id = self.id
                membership.action_activate()
                _logger.info(
                    "Membership #%s activated after payment of invoice %s",
                    membership.id, self.name,
                )
            except Exception:
                _logger.exception(
                    "Error while activating membership #%s", membership.id
                )
