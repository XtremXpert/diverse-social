import logging

from odoo import _, fields, models

_logger = logging.getLogger(__name__)


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    membership_ids = fields.One2many(
        'club_membership.membership', 'sale_order_id',
        string='Adhésions',
    )
    membership_count = fields.Integer(compute='_compute_membership_count')

    def _compute_membership_count(self):
        for order in self:
            order.membership_count = len(order.membership_ids)

    def action_confirm(self):
        res = super().action_confirm()
        self._create_pending_memberships()
        return res

    def _create_pending_memberships(self):
        Membership = self.env['club_membership.membership']
        today = fields.Date.today()
        for order in self:
            partner = order.partner_invoice_id or order.partner_id
            for line in order.order_line:
                mtype = line.product_id.product_tmpl_id.membership_type_id
                if not mtype:
                    continue
                # Avoid duplicate pending memberships for same partner + type + order
                existing = Membership.search([
                    ('partner_id', '=', partner.id),
                    ('sale_order_id', '=', order.id),
                    ('membership_type_id', '=', mtype.id),
                ], limit=1)
                if existing:
                    continue
                Membership.sudo().create({
                    'partner_id': partner.id,
                    'membership_type_id': mtype.id,
                    'sale_order_id': order.id,
                    'start_date': today,
                    'fee_paid': line.price_subtotal,
                    'state': 'pending',
                    'notes': _("Créée automatiquement depuis la commande %s", order.name),
                })
                _logger.info(
                    "Adhésion %s créée en attente pour %s (commande %s)",
                    mtype.name, partner.name, order.name,
                )

    def action_view_memberships(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Adhésions',
            'res_model': 'club_membership.membership',
            'view_mode': 'list,form',
            'domain': [('sale_order_id', '=', self.id)],
        }


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    # Read-only convenience field for the view
    membership_type_id = fields.Many2one(
        related='product_id.product_tmpl_id.membership_type_id',
        string="Type d'adhésion",
        readonly=True,
    )
