from werkzeug.exceptions import Forbidden

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

    # ── Page principale ────────────────────────────────────────────────────

    @route('/my/vouching', auth='user', website=True)
    def my_vouching(self, **kw):
        user = request.env.user
        Vouching = request.env['social_reputation.vouching'].sudo()
        given = Vouching.search([('sponsor_id', '=', user.id)], order='create_date desc')
        received = Vouching.search([('newcomer_id', '=', user.id)], order='create_date desc')

        connections = _get_user_connections(user)
        already_vouched_ids = given.filtered(lambda v: v.state == 'active').mapped('newcomer_id.id')
        vouchable = connections.filtered(lambda u: u.id not in already_vouched_ids)

        profile = request.env['club_social_profile.profile'].sudo().search(
            [('user_id', '=', user.id)], limit=1
        )
        chain = []
        if profile:
            chain = profile.get_vouching_chain(depth=3)

        return request.render('social_reputation.portal_my_vouching', {
            'given': given,
            'received': received,
            'vouchable': vouchable,
            'chain': chain,
            'page_name': 'vouching',
            'error': kw.get('error'),
        })

    # ── Parrainer ──────────────────────────────────────────────────────────

    @route('/my/vouching/give', auth='user', methods=['POST'], website=True, csrf=True)
    def vouching_give(self, newcomer_id='', statement='', **kw):
        user = request.env.user
        if not newcomer_id:
            return request.redirect('/my/vouching?error=newcomer_required')
        try:
            nid = int(newcomer_id)
        except (ValueError, TypeError):
            return request.redirect('/my/vouching?error=newcomer_required')

        connections = _get_user_connections(user)
        newcomer = request.env['res.users'].sudo().browse(nid)
        if not newcomer.exists() or newcomer not in connections:
            return request.redirect('/my/vouching?error=not_connected')

        try:
            request.env['social_reputation.vouching'].sudo().with_user(user).vouch_for(
                newcomer, statement=(statement or '').strip() or None
            )
        except UserError as e:
            return request.redirect(f'/my/vouching?error={e}')
        return request.redirect('/my/vouching?vouched=1')

    # ── Retirer un parrainage ──────────────────────────────────────────────

    @route('/my/vouching/<int:vouching_id>/withdraw', auth='user', methods=['POST'],
           website=True, csrf=True)
    def withdraw_vouching(self, vouching_id, reason='', **kw):
        vouching = request.env['social_reputation.vouching'].sudo().browse(vouching_id)
        if not vouching.exists() or vouching.sponsor_id != request.env.user:
            raise Forbidden()
        try:
            vouching.action_withdraw(reason=(reason or '').strip() or None)
        except UserError as e:
            return request.redirect(f'/my/vouching?error={e}')
        return request.redirect('/my/vouching?withdrawn=1')


# ── Helpers module-level ─────────────────────────────────────────────────────

def _get_user_connections(user):
    Connection = request.env['club_social_profile.connection'].sudo()
    sent = Connection.search([('user_id', '=', user.id), ('state', '=', 'accepted')])
    recv = Connection.search([('connected_user_id', '=', user.id), ('state', '=', 'accepted')])
    user_ids = set(sent.mapped('connected_user_id.id')) | set(recv.mapped('user_id.id'))
    if not user_ids:
        return request.env['res.users'].sudo().browse()
    return request.env['res.users'].sudo().browse(list(user_ids))
