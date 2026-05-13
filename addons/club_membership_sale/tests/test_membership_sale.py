from odoo.tests import TransactionCase, tagged


@tagged('club_membership_sale', 'membership_sale')
class TestMembershipSale(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.group_social = cls.env.ref('social_base.group_social_user')
        cls.type_regular = cls.env.ref('club_membership.membership_type_regular')
        cls.type_trial = cls.env.ref('club_membership.membership_type_trial')

        cls.partner = cls.env['res.partner'].create({
            'name': 'Jean Membre Sale', 'email': 'jean@sale.test',
        })
        cls.user = cls.env['res.users'].create({
            'name': 'Jean Membre Sale', 'login': 'jms_user',
            'email': 'jean@sale.test', 'partner_id': cls.partner.id,
        })

        # Produit d'adhésion annuelle
        cls.product_regular = cls.env['product.template'].create({
            'name': 'Adhésion Annuelle Test',
            'type': 'service',
            'membership_type_id': cls.type_regular.id,
            'list_price': 100.0,
        })
        # Produit sans adhésion
        cls.product_normal = cls.env['product.template'].create({
            'name': 'Produit Normal Test',
            'type': 'service',
            'list_price': 50.0,
        })

        cls.Membership = cls.env['club_membership.membership']

    def _make_order(self, products):
        order = self.env['sale.order'].create({
            'partner_id': self.partner.id,
            'order_line': [
                (0, 0, {
                    'product_id': tmpl.product_variant_ids[:1].id,
                    'product_uom_qty': 1,
                    'price_unit': tmpl.list_price,
                }) for tmpl in products
            ],
        })
        return order

    # ── Création de l'adhésion à la confirmation ──────────────────────────────

    def test_confirm_creates_pending_membership(self):
        order = self._make_order([self.product_regular])
        order.action_confirm()
        pending = self.Membership.search([
            ('partner_id', '=', self.partner.id),
            ('sale_order_id', '=', order.id),
            ('state', '=', 'pending'),
        ])
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending.membership_type_id, self.type_regular)

    def test_confirm_non_membership_product_creates_nothing(self):
        order = self._make_order([self.product_normal])
        before = self.Membership.search_count([('partner_id', '=', self.partner.id)])
        order.action_confirm()
        after = self.Membership.search_count([('partner_id', '=', self.partner.id)])
        self.assertEqual(before, after)

    def test_confirm_mixed_order_creates_one_membership(self):
        order = self._make_order([self.product_regular, self.product_normal])
        order.action_confirm()
        memberships = self.Membership.search([
            ('sale_order_id', '=', order.id),
        ])
        self.assertEqual(len(memberships), 1)

    def test_confirm_idempotent(self):
        order = self._make_order([self.product_regular])
        order.action_confirm()
        count_after_first = self.Membership.search_count([
            ('sale_order_id', '=', order.id)
        ])
        # Calling the internal method again should not duplicate
        order._create_pending_memberships()
        count_after_second = self.Membership.search_count([
            ('sale_order_id', '=', order.id)
        ])
        self.assertEqual(count_after_first, count_after_second)

    def test_fee_paid_set_from_order_line(self):
        order = self._make_order([self.product_regular])
        order.action_confirm()
        membership = self.Membership.search([('sale_order_id', '=', order.id)], limit=1)
        self.assertAlmostEqual(membership.fee_paid, 100.0, places=2)

    def test_no_social_access_on_pending(self):
        order = self._make_order([self.product_regular])
        order.action_confirm()
        self.assertNotIn(self.group_social, self.user.sudo().groups_id)

    # ── Activation au paiement de la facture ──────────────────────────────────

    def test_invoice_paid_activates_membership(self):
        order = self._make_order([self.product_regular])
        order.action_confirm()
        membership = self.Membership.search([('sale_order_id', '=', order.id)], limit=1)
        self.assertEqual(membership.state, 'pending')

        # Simuler le paiement : appel direct à la méthode interne
        invoice = self.env['account.move'].sudo().create({
            'move_type': 'out_invoice',
            'partner_id': self.partner.id,
            'invoice_line_ids': [(0, 0, {
                'name': 'Adhésion',
                'quantity': 1,
                'price_unit': 100.0,
            })],
        })
        invoice.action_post()
        # Lier la commande à la facture
        order.sudo().write({'invoice_ids': [(4, invoice.id)]})

        # Simuler payment_state = 'paid' en appelant la méthode directement
        invoice.sudo()._activate_memberships_on_payment()

        membership.invalidate_recordset()
        self.assertEqual(membership.state, 'active')

    def test_invoice_paid_grants_social_access(self):
        order = self._make_order([self.product_regular])
        order.action_confirm()

        invoice = self.env['account.move'].sudo().create({
            'move_type': 'out_invoice',
            'partner_id': self.partner.id,
            'invoice_line_ids': [(0, 0, {
                'name': 'Adhésion',
                'quantity': 1,
                'price_unit': 100.0,
            })],
        })
        invoice.action_post()
        order.sudo().write({'invoice_ids': [(4, invoice.id)]})
        invoice.sudo()._activate_memberships_on_payment()

        self.assertIn(self.group_social, self.user.sudo().groups_id)

    # ── Stat button & stat count ──────────────────────────────────────────────

    def test_membership_count_on_order(self):
        order = self._make_order([self.product_regular])
        self.assertEqual(order.membership_count, 0)
        order.action_confirm()
        self.assertEqual(order.membership_count, 1)

    def test_action_view_memberships_returns_action(self):
        order = self._make_order([self.product_regular])
        order.action_confirm()
        action = order.action_view_memberships()
        self.assertEqual(action['res_model'], 'club_membership.membership')
        self.assertIn(('sale_order_id', '=', order.id), action['domain'])

    # ── Produit : champ membership_type_id ───────────────────────────────────

    def test_product_membership_type_id(self):
        self.assertEqual(self.product_regular.membership_type_id, self.type_regular)

    def test_product_without_membership_type(self):
        self.assertFalse(self.product_normal.membership_type_id)

    # ── Données seed ─────────────────────────────────────────────────────────

    def test_seed_products_have_membership_type(self):
        p = self.env.ref('club_membership_sale.product_membership_regular')
        self.assertTrue(p.membership_type_id)

    def test_seed_trial_product(self):
        p = self.env.ref('club_membership_sale.product_membership_trial')
        self.assertEqual(p.membership_type_id, self.type_trial)
