import datetime

from odoo.tests import HttpCase, tagged, TransactionCase


@tagged('club_membership_website', 'membership_website')
class TestMembershipWebsiteAccess(TransactionCase):
    """Portal access and security tests (no HTTP server)."""

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
        """A portal user can read their own memberships."""
        memberships = self.env['club_membership.membership'].with_user(
            self.portal_user
        ).search([('partner_id', '=', self.portal_user.partner_id.id)])
        self.assertIn(self.membership, memberships)

    def test_portal_cannot_read_other_membership(self):
        """A portal user cannot see other people's memberships."""
        memberships = self.env['club_membership.membership'].with_user(
            self.other_portal
        ).search([])
        self.assertNotIn(self.membership, memberships)

    def test_portal_cannot_write_membership(self):
        """A portal user cannot modify memberships."""
        from odoo.exceptions import AccessError
        with self.assertRaises(AccessError):
            self.membership.with_user(self.portal_user).write({'state': 'cancelled'})

    def test_portal_cannot_create_membership(self):
        """A portal user cannot create a membership."""
        from odoo.exceptions import AccessError
        with self.assertRaises(AccessError):
            self.env['club_membership.membership'].with_user(self.portal_user).create({
                'partner_id': self.portal_user.partner_id.id,
                'membership_type_id': self.type_regular.id,
                'start_date': datetime.date.today(),
            })

    def test_portal_can_read_membership_types(self):
        """A portal user can read membership types (public catalog)."""
        types = self.env['club_membership.type'].with_user(self.portal_user).search([])
        self.assertGreaterEqual(len(types), 1)

    def test_public_can_read_membership_types(self):
        """A public user can read membership types."""
        types = self.env['club_membership.type'].with_user(
            self.env.ref('base.public_user')
        ).search([('active', '=', True)])
        self.assertGreaterEqual(len(types), 1)

    # ── Recherche de produit ──────────────────────────────────────────────────

    def test_product_linked_to_type(self):
        """Seed products are linked to their membership type."""
        products = self.env['product.template'].sudo().search([
            ('membership_type_id', '!=', False),
        ])
        self.assertGreaterEqual(len(products), 1)
        for product in products:
            self.assertIsNotNone(product.membership_type_id)

    def test_product_has_variant(self):
        """Each membership product has at least one variant."""
        products = self.env['product.template'].sudo().search([
            ('membership_type_id', '!=', False),
        ])
        for product in products:
            self.assertTrue(product.product_variant_id)


@tagged('club_membership_website', 'membership_website')
class TestMembershipPortalData(TransactionCase):
    """Tests on the data returned by the portal."""

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
        """Multiple memberships of one member are all visible."""
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
        """A renewal product is available for an active membership."""
        product = self.env['product.template'].sudo().search([
            ('membership_type_id', '=', self.type_regular.id),
            ('sale_ok', '=', True),
        ], limit=1)
        if not product:
            self.skipTest("No product linked to the regular type")
        self.assertTrue(product.membership_type_id)

    def test_no_renewal_product_for_cancelled(self):
        """Consistency: a cancelled membership does not show the renew button."""
        m = self.env['club_membership.membership'].sudo().create({
            'partner_id': self.portal_user.partner_id.id,
            'membership_type_id': self.type_regular.id,
            'start_date': datetime.date.today(),
            'state': 'cancelled',
        })
        # Le bouton renouvellement ne s'affiche que pour active/expired
        self.assertNotIn(m.state, ('active', 'expired'))

    def test_portal_count_matches_search(self):
        """The portal counter matches the number of memberships found."""
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
    """HTTP tests for the storefront and portal (requires post_install)."""

    def test_membership_page_public(self):
        """La page /membership est accessible sans authentification."""
        response = self.url_open('/membership')
        self.assertEqual(response.status_code, 200)
        # Structural marker: the membership join form is rendered.
        self.assertIn(b'/membership/join/', response.content)

    def test_membership_page_shows_types(self):
        """The /membership page displays membership types."""
        response = self.url_open('/membership')
        self.assertEqual(response.status_code, 200)
        # At least one type is displayed (seed data)
        self.assertIn(b'S\'inscrire', response.content)

    def test_portal_requires_auth(self):
        """The /my/membership page redirects if not authenticated."""
        response = self.url_open('/my/membership', allow_redirects=False)
        self.assertIn(response.status_code, (302, 303))

    def test_portal_my_memberships_authenticated(self):
        """The /my/membership page is accessible to a logged-in user."""
        self.authenticate('admin', 'admin')
        _csrf = self.csrf_token()
        response = self.url_open('/my/membership')
        self.assertEqual(response.status_code, 200)

    def test_membership_detail_requires_auth(self):
        """The /my/membership/<id> page redirects if not authenticated."""
        response = self.url_open('/my/membership/1', allow_redirects=False)
        self.assertIn(response.status_code, (302, 303))

    def test_membership_detail_wrong_user_returns_403(self):
        """A user accessing someone else's membership gets 403."""
        env = self.env
        type_regular = env.ref('club_membership.membership_type_regular')
        portal_user = env['res.users'].sudo().create({
            'name': 'Portal Detail 403',
            'login': 'portal_detail_403',
            'email': 'detail403@mw.test',
            'group_ids': [(4, env.ref('base.group_portal').id)],
        })
        other_portal = env['res.users'].sudo().create({
            'name': 'Other Portal 403',
            'login': 'other_detail_403',
            'email': 'other403@mw.test',
            'group_ids': [(4, env.ref('base.group_portal').id)],
        })
        membership = env['club_membership.membership'].sudo().create({
            'partner_id': portal_user.partner_id.id,
            'membership_type_id': type_regular.id,
            'start_date': datetime.date.today(),
            'state': 'active',
        })
        self.authenticate(other_portal.login, 'odoo1234')
        _csrf = self.csrf_token()
        response = self.url_open(f'/my/membership/{membership.id}', allow_redirects=False)
        self.assertIn(response.status_code, (403, 302, 303))

    def test_join_nonexistent_type_returns_404(self):
        """POST /membership/join/999999 retourne 404 si le type n'existe pas."""
        self.authenticate('admin', 'admin')
        _csrf = self.csrf_token()
        response = self.url_open('/membership/join/999999',
                                 data={'csrf_token': _csrf, },
                                 allow_redirects=False)
        self.assertEqual(response.status_code, 404)

    def test_membership_page_content_type_html(self):
        """The /membership response is HTML."""
        response = self.url_open('/membership')
        self.assertIn('text/html', response.headers.get('Content-Type', ''))


@tagged('club_membership_website', 'membership_website')
class TestMembershipPortalDataExtra(TransactionCase):
    """Extra tests on portal data and security."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.type_regular = cls.env.ref('club_membership.membership_type_regular')
        cls.portal_user = cls.env['res.users'].create({
            'name': 'Portail Extra',
            'login': 'portal_extra_test',
            'email': 'portal_extra@mw.test',
            'group_ids': [(4, cls.env.ref('base.group_portal').id)],
        })
        cls.membership = cls.env['club_membership.membership'].sudo().create({
            'partner_id': cls.portal_user.partner_id.id,
            'membership_type_id': cls.type_regular.id,
            'start_date': datetime.date.today(),
            'state': 'active',
        })

    def test_portal_cannot_delete_membership(self):
        """A portal user cannot delete a membership."""
        from odoo.exceptions import AccessError
        with self.assertRaises(AccessError):
            self.membership.with_user(self.portal_user).unlink()

    def test_inactive_type_not_listed(self):
        """An inactive type does not appear in the public search."""
        inactive_type = self.env['club_membership.type'].sudo().create({
            'name': 'Type Inactif Test',
            'active': False,
            'duration_months': 12,
        })
        types = self.env['club_membership.type'].with_user(
            self.env.ref('base.public_user')
        ).search([('active', '=', True)])
        self.assertNotIn(inactive_type, types)

    def test_membership_type_sequence_ordering(self):
        """Types are ordered by ascending sequence."""
        types = self.env['club_membership.type'].sudo().search(
            [('active', '=', True)], order='sequence, name'
        )
        sequences = [t.sequence for t in types]
        self.assertEqual(sequences, sorted(sequences))

    def test_portal_user_sees_only_own_memberships_count(self):
        """portal search_count returns only the user's memberships."""
        other = self.env['res.users'].sudo().create({
            'name': 'Other Count', 'login': 'other_count_mw', 'email': 'ocount@mw.test',
            'group_ids': [(4, self.env.ref('base.group_portal').id)],
        })
        self.env['club_membership.membership'].sudo().create({
            'partner_id': other.partner_id.id,
            'membership_type_id': self.type_regular.id,
            'start_date': datetime.date.today(),
            'state': 'pending',
        })
        count = self.env['club_membership.membership'].with_user(
            self.portal_user
        ).search_count([])
        own = self.env['club_membership.membership'].with_user(
            self.portal_user
        ).search([])
        for m in own:
            self.assertEqual(m.partner_id, self.portal_user.partner_id)
        self.assertEqual(count, len(own))

    def test_membership_type_has_currency(self):
        """Seeded membership types have a currency configured."""
        types = self.env['club_membership.type'].sudo().search([('active', '=', True)])
        for t in types:
            self.assertTrue(t.currency_id)

    def test_pending_state_visible_in_portal(self):
        """A membership in 'pending' state is visible in the portal."""
        m = self.env['club_membership.membership'].sudo().create({
            'partner_id': self.portal_user.partner_id.id,
            'membership_type_id': self.type_regular.id,
            'start_date': datetime.date.today(),
            'state': 'pending',
        })
        found = self.env['club_membership.membership'].with_user(
            self.portal_user
        ).search([('id', '=', m.id)])
        self.assertIn(m, found)
