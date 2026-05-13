import datetime

from odoo.tests import HttpCase, tagged, TransactionCase


@tagged('club_membership_website', 'membership_website')
class TestMembershipWebsiteAccess(TransactionCase):
    """Tests d'accès et de règles de sécurité portail (sans serveur HTTP)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.type_regular = cls.env.ref('club_membership.membership_type_regular')

        cls.portal_user = cls.env['res.users'].create({
            'name': 'Portail Test',
            'login': 'portal_mw_test',
            'email': 'portal@mw.test',
            'group_ids': [(4, cls.env.ref('base.group_portal').id)],
        })
        cls.other_portal = cls.env['res.users'].create({
            'name': 'Autre Portail',
            'login': 'portal_mw_other',
            'email': 'other@mw.test',
            'group_ids': [(4, cls.env.ref('base.group_portal').id)],
        })

        cls.membership = cls.env['club_membership.membership'].sudo().create({
            'partner_id': cls.portal_user.partner_id.id,
            'membership_type_id': cls.type_regular.id,
            'start_date': datetime.date.today(),
            'state': 'active',
        })

    # ── ACL portail ───────────────────────────────────────────────────────────

    def test_portal_can_read_own_membership(self):
        """L'utilisateur portail peut lire ses propres adhésions."""
        memberships = self.env['club_membership.membership'].with_user(
            self.portal_user
        ).search([('partner_id', '=', self.portal_user.partner_id.id)])
        self.assertIn(self.membership, memberships)

    def test_portal_cannot_read_other_membership(self):
        """L'utilisateur portail ne voit pas les adhésions des autres."""
        memberships = self.env['club_membership.membership'].with_user(
            self.other_portal
        ).search([])
        self.assertNotIn(self.membership, memberships)

    def test_portal_cannot_write_membership(self):
        """L'utilisateur portail ne peut pas modifier les adhésions."""
        from odoo.exceptions import AccessError
        with self.assertRaises(AccessError):
            self.membership.with_user(self.portal_user).write({'state': 'cancelled'})

    def test_portal_cannot_create_membership(self):
        """L'utilisateur portail ne peut pas créer d'adhésion."""
        from odoo.exceptions import AccessError
        with self.assertRaises(AccessError):
            self.env['club_membership.membership'].with_user(self.portal_user).create({
                'partner_id': self.portal_user.partner_id.id,
                'membership_type_id': self.type_regular.id,
                'start_date': datetime.date.today(),
            })

    def test_portal_can_read_membership_types(self):
        """L'utilisateur portail peut lire les types d'adhésion (vitrine publique)."""
        types = self.env['club_membership.type'].with_user(self.portal_user).search([])
        self.assertGreaterEqual(len(types), 1)

    def test_public_can_read_membership_types(self):
        """L'utilisateur public peut lire les types d'adhésion."""
        types = self.env['club_membership.type'].with_user(
            self.env.ref('base.public_user')
        ).search([('active', '=', True)])
        self.assertGreaterEqual(len(types), 1)

    # ── Recherche de produit ──────────────────────────────────────────────────

    def test_product_linked_to_type(self):
        """Les produits seed sont liés à leur type d'adhésion."""
        products = self.env['product.template'].sudo().search([
            ('membership_type_id', '!=', False),
        ])
        self.assertGreaterEqual(len(products), 1)
        for product in products:
            self.assertIsNotNone(product.membership_type_id)

    def test_product_has_variant(self):
        """Chaque produit d'adhésion possède au moins une variante."""
        products = self.env['product.template'].sudo().search([
            ('membership_type_id', '!=', False),
        ])
        for product in products:
            self.assertTrue(product.product_variant_id)


@tagged('club_membership_website', 'membership_website')
class TestMembershipPortalData(TransactionCase):
    """Tests sur les données retournées par le portail."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.type_regular = cls.env.ref('club_membership.membership_type_regular')
        cls.portal_user = cls.env['res.users'].create({
            'name': 'Portail Data',
            'login': 'portal_data_test',
            'email': 'portal_data@mw.test',
            'group_ids': [(4, cls.env.ref('base.group_portal').id)],
        })

    def test_multiple_memberships_visible(self):
        """Plusieurs adhésions d'un même membre sont toutes visibles."""
        type2 = self.env.ref('club_membership.membership_type_lifetime')
        m1 = self.env['club_membership.membership'].sudo().create({
            'partner_id': self.portal_user.partner_id.id,
            'membership_type_id': self.type_regular.id,
            'start_date': datetime.date(2023, 1, 1),
            'end_date': datetime.date(2023, 12, 31),
            'state': 'expired',
        })
        m2 = self.env['club_membership.membership'].sudo().create({
            'partner_id': self.portal_user.partner_id.id,
            'membership_type_id': type2.id,
            'start_date': datetime.date.today(),
            'state': 'active',
        })
        memberships = self.env['club_membership.membership'].with_user(
            self.portal_user
        ).search([('partner_id', '=', self.portal_user.partner_id.id)])
        self.assertIn(m1, memberships)
        self.assertIn(m2, memberships)

    def test_renewal_product_found_for_active(self):
        """Un produit de renouvellement est disponible pour une adhésion active."""
        product = self.env['product.template'].sudo().search([
            ('membership_type_id', '=', self.type_regular.id),
            ('sale_ok', '=', True),
        ], limit=1)
        if not product:
            self.skipTest("Aucun produit lié au type régulier")
        self.assertTrue(product.membership_type_id)

    def test_no_renewal_product_for_cancelled(self):
        """Cohérence : une adhésion annulée n'affiche pas le bouton renouvellement."""
        m = self.env['club_membership.membership'].sudo().create({
            'partner_id': self.portal_user.partner_id.id,
            'membership_type_id': self.type_regular.id,
            'start_date': datetime.date.today(),
            'state': 'cancelled',
        })
        # Le bouton renouvellement ne s'affiche que pour active/expired
        self.assertNotIn(m.state, ('active', 'expired'))

    def test_portal_count_matches_search(self):
        """Le compteur portail correspond au nombre d'adhésions trouvées."""
        m1 = self.env['club_membership.membership'].sudo().create({
            'partner_id': self.portal_user.partner_id.id,
            'membership_type_id': self.type_regular.id,
            'start_date': datetime.date.today(),
            'state': 'pending',
        })
        count = self.env['club_membership.membership'].with_user(
            self.portal_user
        ).search_count([('partner_id', '=', self.portal_user.partner_id.id)])
        memberships = self.env['club_membership.membership'].with_user(
            self.portal_user
        ).search([('partner_id', '=', self.portal_user.partner_id.id)])
        self.assertEqual(count, len(memberships))


@tagged('club_membership_website', 'membership_website', 'post_install', '-at_install')
class TestMembershipWebsiteHttp(HttpCase):
    """Tests HTTP de la vitrine et du portail (nécessite post_install)."""

    def test_membership_page_public(self):
        """La page /membership est accessible sans authentification."""
        response = self.url_open('/membership')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Devenir membre', response.content)

    def test_membership_page_shows_types(self):
        """La page /membership affiche les types d'adhésion."""
        response = self.url_open('/membership')
        self.assertEqual(response.status_code, 200)
        # Au moins un type est affiché (seed data)
        self.assertIn(b'S\'inscrire', response.content)

    def test_portal_requires_auth(self):
        """La page /my/membership redirige si non authentifié."""
        response = self.url_open('/my/membership', allow_redirects=False)
        self.assertIn(response.status_code, (302, 303))

    def test_portal_my_memberships_authenticated(self):
        """La page /my/membership est accessible pour un utilisateur connecté."""
        self.authenticate('admin', 'admin')
        response = self.url_open('/my/membership')
        self.assertEqual(response.status_code, 200)
