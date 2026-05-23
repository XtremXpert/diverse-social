import datetime

from odoo.tests import TransactionCase, tagged


@tagged('club_event_combo')
class TestEventComboSaleLine(TransactionCase):
    """Sale line auto-binding for event-ticket products in combos."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env['res.partner'].create({'name': 'Combo Buyer'})
        now = datetime.datetime.now()
        cls.event = cls.env['event.event'].create({
            'name': 'Combo Event',
            'date_begin': now,
            'date_end': now + datetime.timedelta(hours=2),
        })
        cls.ticket_product = cls.env['product.product'].create({
            'name': 'Combo Ticket Product',
            'service_tracking': 'event',
            'type': 'service',
            'list_price': 10.0,
        })
        cls.ticket = cls.env['event.event.ticket'].create({
            'name': 'Standard',
            'event_id': cls.event.id,
            'product_id': cls.ticket_product.id,
        })
        cls.plain_product = cls.env['product.product'].create({
            'name': 'Plain Product',
            'type': 'consu',
            'list_price': 5.0,
        })

    def _order(self):
        return self.env['sale.order'].create({'partner_id': self.partner.id})

    def _line(self, order, product):
        return self.env['sale.order.line'].create({
            'order_id': order.id,
            'product_id': product.id,
        })

    # ── _compute_event_id ────────────────────────────────────────────────

    def test_event_product_auto_assigns_event(self):
        line = self._line(self._order(), self.ticket_product)
        self.assertEqual(line.event_id, self.event)

    def test_plain_product_does_not_assign_event(self):
        line = self._line(self._order(), self.plain_product)
        self.assertFalse(line.event_id)

    # ── _compute_event_related ───────────────────────────────────────────

    def test_event_product_auto_assigns_ticket(self):
        line = self._line(self._order(), self.ticket_product)
        self.assertEqual(line.event_ticket_id, self.ticket)


@tagged('club_event_combo')
class TestEventComboWebsite(TransactionCase):
    """Website product domain excludes event-ticket products."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.website = cls.env['website'].search([], limit=1) or cls.env['website'].create({'name': 'Test'})
        cls.ticket_product = cls.env['product.product'].create({
            'name': 'Domain Ticket',
            'service_tracking': 'event',
            'type': 'service',
            'list_price': 10.0,
            'is_published': True,
        })
        cls.plain_product = cls.env['product.product'].create({
            'name': 'Domain Plain',
            'type': 'consu',
            'list_price': 5.0,
            'is_published': True,
        })

    def test_product_domain_excludes_event_ticket(self):
        domain = self.website._product_domain()
        # The domain is a list of leaves applied to product.template
        templates = self.env['product.template'].search(domain)
        self.assertNotIn(self.ticket_product.product_tmpl_id, templates)
        self.assertIn(self.plain_product.product_tmpl_id, templates)
