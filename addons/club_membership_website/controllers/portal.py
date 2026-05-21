from werkzeug.exceptions import Forbidden

from odoo.http import request, route
from odoo.addons.portal.controllers.portal import CustomerPortal, pager as portal_pager


class ClubMembershipPortal(CustomerPortal):

    def _prepare_home_portal_values(self, counters):
        values = super()._prepare_home_portal_values(counters)
        if 'membership_count' in counters:
            values['membership_count'] = request.env['club_membership.membership'].search_count(
                [('partner_id', '=', request.env.user.partner_id.id)]
            )
        return values

    @route('/my/membership', auth='user', website=True)
    def my_memberships(self, page=1, **kw):
        """List of memberships for the connected member."""
        partner = request.env.user.partner_id
        Membership = request.env['club_membership.membership']

        domain = [('partner_id', '=', partner.id)]
        total = Membership.search_count(domain)
        pager = portal_pager(
            url='/my/membership',
            total=total,
            page=page,
            step=10,
        )
        memberships = Membership.search(
            domain,
            order='start_date desc',
            limit=10,
            offset=pager['offset'],
        )
        return request.render('club_membership_website.portal_my_memberships', {
            'memberships': memberships,
            'pager': pager,
            'page_name': 'membership',
        })

    @route('/my/membership/<int:membership_id>', auth='user', website=True)
    def membership_detail(self, membership_id, **kw):
        """Membership detail."""
        membership = request.env['club_membership.membership'].browse(membership_id).exists()
        if not membership or membership.partner_id != request.env.user.partner_id:
            raise Forbidden()

        # Chercher le produit de renouvellement si disponible
        renewal_product = None
        if membership.state in ('active', 'expired'):
            renewal_product = request.env['product.template'].sudo().search([
                ('membership_type_id', '=', membership.membership_type_id.id),
                ('sale_ok', '=', True),
            ], limit=1)

        return request.render('club_membership_website.portal_membership_detail', {
            'membership': membership,
            'renewal_product': renewal_product,
            'page_name': 'membership',
        })

    @route('/my/membership/<int:membership_id>/renew', auth='user', website=True, methods=['POST'], csrf=True)
    def membership_renew(self, membership_id, **kw):
        """Ajoute le renouvellement au panier."""
        membership = request.env['club_membership.membership'].browse(membership_id).exists()
        if not membership or membership.partner_id != request.env.user.partner_id:
            raise Forbidden()

        product = request.env['product.template'].sudo().search([
            ('membership_type_id', '=', membership.membership_type_id.id),
            ('sale_ok', '=', True),
        ], limit=1)
        if not product:
            return request.redirect(f'/my/membership/{membership_id}')

        variant = product.product_variant_id
        if not variant:
            return request.redirect(f'/my/membership/{membership_id}')

        order_sudo = request.cart or request.website._create_cart()
        order_sudo.with_context(skip_cart_verification=True)._cart_add(
            product_id=variant.id,
            quantity=1,
        )
        return request.redirect('/shop/cart')
