from datetime import timedelta

from werkzeug.exceptions import Forbidden, NotFound

from odoo import fields
from odoo.exceptions import UserError
from odoo.http import request, route
from odoo.addons.portal.controllers.portal import CustomerPortal, pager as portal_pager


_STATE_LABELS = {
    'draft': 'Brouillon',
    'open': 'Ouvert',
    'voting': 'En vote',
    'accepted': 'Acceptée',
    'rejected': 'Rejetée',
    'withdrawn': 'Retirée',
}


class GovernancePortal(CustomerPortal):

    def _prepare_home_portal_values(self, counters):
        values = super()._prepare_home_portal_values(counters)
        if 'proposals_voting_count' in counters:
            values['proposals_voting_count'] = request.env['social_governance.proposal'].sudo().search_count([
                ('state', '=', 'voting'),
            ])
        return values

    # ── Liste ──────────────────────────────────────────────────────────────────

    @route('/governance', auth='user', website=True, sitemap=True)
    def governance_list(self, page=1, state='voting', **kw):
        Proposal = request.env['social_governance.proposal'].sudo()
        valid_states = list(_STATE_LABELS.keys())
        if state not in valid_states:
            state = 'voting'
        domain = [('state', '=', state)]
        total = Proposal.search_count(domain)
        pager = portal_pager(
            url='/governance', url_args={'state': state},
            total=total, page=page, step=10,
        )
        proposals = Proposal.search(domain, order='create_date desc', limit=10, offset=pager['offset'])
        categories = request.env['social_governance.proposal_category'].sudo().search([])
        return request.render('social_governance.portal_governance_list', {
            'proposals': proposals,
            'pager': pager,
            'state_filter': state,
            'state_labels': _STATE_LABELS,
            'categories': categories,
            'page_name': 'governance',
            'error': kw.get('error'),
        })

    # ── Créer une proposition ──────────────────────────────────────────────────

    @route('/governance/create', auth='user', methods=['POST'], website=True, csrf=True)
    def governance_create(self, name='', description='', category_id='',
                          voting_closes_at='', **kw):
        name = (name or '').strip()
        description = (description or '').strip()
        if not name or not description:
            return request.redirect('/governance?error=fields_required')
        try:
            cat_id = int(category_id)
        except (ValueError, TypeError):
            return request.redirect('/governance?error=category_required')

        category = request.env['social_governance.proposal_category'].sudo().browse(cat_id)
        if not category.exists():
            return request.redirect('/governance?error=category_required')

        closes = None
        if voting_closes_at:
            try:
                closes = fields.Datetime.from_string(voting_closes_at)
            except Exception:
                closes = None

        vals = {
            'name': name,
            'description': f'<p>{description}</p>',
            'author_id': request.env.user.id,
            'category_id': cat_id,
        }
        if closes:
            vals['voting_closes_at'] = closes

        try:
            proposal = request.env['social_governance.proposal'].sudo().with_user(
                request.env.user
            ).create(vals)
        except Exception:
            return request.redirect('/governance?error=create_failed')
        return request.redirect(f'/governance/{proposal.id}?created=1')

    # ── Détail ─────────────────────────────────────────────────────────────────

    @route('/governance/<int:proposal_id>', auth='user', website=True)
    def governance_detail(self, proposal_id, **kw):
        proposal = request.env['social_governance.proposal'].sudo().browse(proposal_id).exists()
        if not proposal:
            raise NotFound()
        user = request.env.user
        my_vote = proposal.vote_ids.filtered(lambda v: v.voter_id == user)
        is_author = proposal.author_id == user
        is_moderator = user.has_group('social_base.group_social_moderator')
        deadline_hours = None
        if proposal.state == 'voting' and proposal.voting_closes_at:
            delta = proposal.voting_closes_at - fields.Datetime.now()
            deadline_hours = max(0, int(delta.total_seconds() // 3600))
        return request.render('social_governance.portal_governance_detail', {
            'proposal': proposal,
            'my_vote': my_vote[:1].choice if my_vote else False,
            'state_labels': _STATE_LABELS,
            'is_author': is_author,
            'is_moderator': is_moderator,
            'deadline_hours': deadline_hours,
            'page_name': 'governance',
            'error': kw.get('error'),
        })

    # ── Voter ──────────────────────────────────────────────────────────────────

    @route('/governance/<int:proposal_id>/vote', auth='user', methods=['POST'],
           website=True, csrf=True)
    def governance_vote(self, proposal_id, choice='abstain', **kw):
        proposal = request.env['social_governance.proposal'].sudo().browse(proposal_id).exists()
        if not proposal or proposal.state != 'voting':
            raise NotFound()
        if choice not in ('yes', 'no', 'abstain'):
            return request.redirect(f'/governance/{proposal_id}?error=invalid_choice')
        try:
            proposal.with_user(request.env.user).action_vote(choice)
        except UserError as e:
            return request.redirect(f'/governance/{proposal_id}?error={e}')
        return request.redirect(f'/governance/{proposal_id}?voted=1')

    # ── Ouvrir une proposition ────────────────────────────────────────────────

    @route('/governance/<int:proposal_id>/open', auth='user', methods=['POST'],
           website=True, csrf=True)
    def governance_open(self, proposal_id, **kw):
        proposal = request.env['social_governance.proposal'].sudo().browse(proposal_id).exists()
        if not proposal:
            raise NotFound()
        user = request.env.user
        if proposal.author_id != user and not user.has_group('social_base.group_social_moderator'):
            raise Forbidden()
        try:
            proposal.with_user(user).action_open()
        except UserError as e:
            return request.redirect(f'/governance/{proposal_id}?error={e}')
        return request.redirect(f'/governance/{proposal_id}?opened=1')

    # ── Lancer le vote ────────────────────────────────────────────────────────

    @route('/governance/<int:proposal_id>/start_voting', auth='user', methods=['POST'],
           website=True, csrf=True)
    def governance_start_voting(self, proposal_id, voting_closes_at='', **kw):
        proposal = request.env['social_governance.proposal'].sudo().browse(proposal_id).exists()
        if not proposal:
            raise NotFound()
        user = request.env.user
        if proposal.author_id != user and not user.has_group('social_base.group_social_moderator'):
            raise Forbidden()
        if voting_closes_at:
            try:
                closes = fields.Datetime.from_string(voting_closes_at)
                proposal.sudo().write({'voting_closes_at': closes})
            except Exception:
                return request.redirect(f'/governance/{proposal_id}?error=invalid_date')
        try:
            proposal.with_user(user).action_start_voting()
        except UserError as e:
            return request.redirect(f'/governance/{proposal_id}?error={e}')
        return request.redirect(f'/governance/{proposal_id}?voting_started=1')

    # ── Retirer une proposition ────────────────────────────────────────────────

    @route('/governance/<int:proposal_id>/withdraw', auth='user', methods=['POST'],
           website=True, csrf=True)
    def governance_withdraw(self, proposal_id, **kw):
        proposal = request.env['social_governance.proposal'].sudo().browse(proposal_id).exists()
        if not proposal:
            raise NotFound()
        user = request.env.user
        if proposal.author_id != user and not user.has_group('social_base.group_social_moderator'):
            raise Forbidden()
        try:
            proposal.with_user(user).action_withdraw()
        except UserError as e:
            return request.redirect(f'/governance/{proposal_id}?error={e}')
        return request.redirect(f'/governance/{proposal_id}?withdrawn=1')

    # ── Journal des décisions ──────────────────────────────────────────────────

    @route('/governance/log', auth='user', website=True, sitemap=True)
    def governance_log(self, page=1, **kw):
        Log = request.env['social_governance.decision_log'].sudo()
        domain = [('is_public', '=', True)]
        total = Log.search_count(domain)
        pager = portal_pager(url='/governance/log', total=total, page=page, step=20)
        entries = Log.search(domain, order='decision_date desc', limit=20, offset=pager['offset'])
        return request.render('social_governance.portal_governance_log', {
            'entries': entries,
            'pager': pager,
            'page_name': 'governance',
            'error': kw.get('error'),
        })
