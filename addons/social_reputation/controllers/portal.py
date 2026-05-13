from werkzeug.exceptions import Forbidden, NotFound

from odoo import _
from odoo.exceptions import UserError
from odoo.http import request, route
from odoo.addons.portal.controllers.portal import CustomerPortal


class ReputationPortal(CustomerPortal):

    def _prepare_home_portal_values(self, counters):
        values = super()._prepare_home_portal_values(counters)
        if 'vouching_count' in counters:
            values['vouching_count'] = request.env['social_reputation.vouching'].search_count([
                '|',
                ('sponsor_id', '=', request.env.user.id),
                ('newcomer_id', '=', request.env.user.id),
                ('state', '=', 'active'),
            ])
        return values

    @route('/my/vouching', auth='user', website=True)
    def my_vouching(self, **kw):
        Vouching = request.env['social_reputation.vouching']
        given = Vouching.search([
            ('sponsor_id', '=', request.env.user.id),
        ], order='create_date desc')
        received = Vouching.search([
            ('newcomer_id', '=', request.env.user.id),
        ], order='create_date desc')
        return request.render('social_reputation.portal_my_vouching', {
            'given': given,
            'received': received,
            'page_name': 'vouching',
        })

    @route('/my/vouching/<int:vouching_id>/withdraw', auth='user', methods=['POST'],
           website=True, csrf=True)
    def withdraw_vouching(self, vouching_id, reason='', **kw):
        vouching = request.env['social_reputation.vouching'].browse(vouching_id).exists()
        if not vouching or vouching.sponsor_id != request.env.user:
            raise Forbidden()
        try:
            vouching.action_withdraw(reason=(reason or '').strip() or None)
        except UserError as e:
            return request.render('social_reputation.portal_my_vouching', {
                'given': request.env['social_reputation.vouching'].search(
                    [('sponsor_id', '=', request.env.user.id)], order='create_date desc'
                ),
                'received': request.env['social_reputation.vouching'].search(
                    [('newcomer_id', '=', request.env.user.id)], order='create_date desc'
                ),
                'error': str(e),
                'page_name': 'vouching',
            })
        return request.redirect('/my/vouching')
