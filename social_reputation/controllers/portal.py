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
        # Vouchings sur des users existants
        given = Vouching.search([
            ('sponsor_id', '=', user.id),
            ('newcomer_id', '!=', False),
        ], order='create_date desc')
        # Invitations en attente (newcomer pas encore inscrit, ou en attente de paiement)
        invitations = Vouching.search([
            ('sponsor_id', '=', user.id),
            ('state', 'in', ['invited', 'pending_payment', 'expired']),
        ], order='create_date desc')
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
            'invitations': invitations,
            'received': received,
            'vouchable': vouchable,
            'chain': chain,
            'page_name': 'vouching',
            'error': kw.get('error'),
        })

    # ── Inviter quelqu'un par email ────────────────────────────────────────

    @route('/my/vouching/invite', auth='user', website=True)
    def vouching_invite_form(self, **kw):
        return request.render('social_reputation.portal_vouching_invite', {
            'page_name': 'vouching_invite',
            'email': kw.get('email', ''),
            'statement': kw.get('statement', ''),
            'error': kw.get('error'),
        })

    @route('/my/vouching/invite/submit', auth='user', methods=['POST'],
           website=True, csrf=True)
    def vouching_invite_submit(self, email='', statement='', **kw):
        email = (email or '').strip()
        statement = (statement or '').strip() or None
        if not email or '@' not in email:
            return request.redirect(
                f'/my/vouching/invite?error=email_invalid&statement={statement or ""}'
            )
        try:
            with request.env.cr.savepoint():
                vouching = request.env['social_reputation.vouching'].with_user(
                    request.env.user,
                ).action_invite_email(email=email, statement=statement)
                vouching.action_send_invitation_email()
        except UserError as e:
            from urllib.parse import quote
            return request.redirect(
                f'/my/vouching/invite?error={quote(str(e))}'
                f'&email={quote(email)}&statement={quote(statement or "")}'
            )
        return request.redirect('/my/vouching?invited=1')

    @route('/my/vouching/invite/<int:vouching_id>/resend', auth='user',
           methods=['POST'], website=True, csrf=True)
    def vouching_invite_resend(self, vouching_id, **kw):
        v = request.env['social_reputation.vouching'].sudo().browse(vouching_id)
        if not v.exists() or v.sponsor_id != request.env.user:
            raise Forbidden()
        if v.state != 'invited':
            return request.redirect('/my/vouching?error=invitation_not_pending')
        try:
            v.action_send_invitation_email()
        except UserError as e:
            from urllib.parse import quote
            return request.redirect(f'/my/vouching?error={quote(str(e))}')
        return request.redirect('/my/vouching?resent=1')

    @route('/my/vouching/invite/<int:vouching_id>/cancel', auth='user',
           methods=['POST'], website=True, csrf=True)
    def vouching_invite_cancel(self, vouching_id, **kw):
        v = request.env['social_reputation.vouching'].sudo().browse(vouching_id)
        if not v.exists() or v.sponsor_id != request.env.user:
            raise Forbidden()
        if v.state not in ('invited', 'pending_payment'):
            return request.redirect('/my/vouching?error=invitation_not_cancellable')
        # Annuler une invitation = withdraw avec raison standard.
        # action_withdraw exige une raison; on en fournit une par défaut.
        try:
            v.with_user(request.env.user).action_withdraw(reason='Cancelled by sponsor')
        except UserError as e:
            from urllib.parse import quote
            return request.redirect(f'/my/vouching?error={quote(str(e))}')
        return request.redirect('/my/vouching?cancelled=1')

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

        # Wrap in a savepoint: vouch_for() does a create() and constraints
        # (circular, self-vouching) raise ValidationError after the INSERT
        # is already in the current transaction. Without a savepoint, the
        # `except UserError` swallows the exception and the partial row
        # gets committed when the controller returns a normal response.
        try:
            with request.env.cr.savepoint():
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
