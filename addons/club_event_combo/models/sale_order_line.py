from odoo import api, models


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    @api.depends('product_id')
    def _compute_event_id(self):
        """Étend le compute standard pour auto-assigner l'événement
        quand le produit est lié à un billet d'événement unique.
        Permet de déclencher l'inscription depuis un combo produit.
        """
        super()._compute_event_id()
        for line in self:
            if line.event_id or not line.product_id:
                continue
            if line.product_id.service_tracking != 'event':
                continue
            ticket = self.env['event.event.ticket'].search(
                [('product_id', '=', line.product_id.id)],
                limit=1,
            )
            if ticket:
                line.event_id = ticket.event_id

    @api.depends('event_id', 'product_id')
    def _compute_event_related(self):
        """Étend le compute standard pour auto-assigner le type de billet
        d'après le produit de la ligne, une fois l'événement identifié.
        """
        super()._compute_event_related()
        for line in self:
            if line.event_ticket_id or not line.event_id or not line.product_id:
                continue
            ticket = line.event_id.event_ticket_ids.filtered(
                lambda t: t.product_id == line.product_id
            )[:1]
            if ticket:
                line.event_ticket_id = ticket
