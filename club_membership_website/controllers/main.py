from werkzeug.exceptions import NotFound

from odoo.http import Controller, request, route


class ClubMembershipWebsite(Controller):

    @route('/membership', auth='public', website=True, sitemap=True)
    def membership_page(self, **kw):
        """Public storefront: list of available membership types."""
        types = request.env['club_membership.type'].sudo().search(
            [('active', '=', True)], order='sequence, name'
        )
        # Associate each type to its website_sale product (first published one found)
        Product = request.env['product.template'].sudo()
        type_products = {}
        for mtype in types:
            product = Product.search([
                ('membership_type_id', '=', mtype.id),
                ('sale_ok', '=', True),
                ('active', '=', True),
            ], limit=1)
            if product:
                type_products[mtype.id] = product

        return request.render('club_membership_website.membership_page', {
            'types': types,
            'type_products': type_products,
        })

    @route('/membership/join/<int:type_id>', auth='public', website=True, methods=['POST'], csrf=True)
    def join_membership(self, type_id, **kw):
        """Add the membership product to the cart and redirect to checkout."""
        mtype = request.env['club_membership.type'].sudo().browse(type_id).exists()
        if not mtype:
            raise NotFound()

        product = request.env['product.template'].sudo().search([
            ('membership_type_id', '=', mtype.id),
            ('sale_ok', '=', True),
            ('active', '=', True),
        ], limit=1)
        if not product:
            return request.redirect('/membership')

        variant = product.product_variant_id
        if not variant:
            return request.redirect('/membership')

        order_sudo = request.cart or request.website._create_cart()
        order_sudo.with_context(skip_cart_verification=True)._cart_add(
            product_id=variant.id,
            quantity=1,
        )
        return request.redirect('/shop/cart')
