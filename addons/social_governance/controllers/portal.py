from werkzeug.exceptions import NotFound

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

_CATEGORY_LABELS = {
    'ban': 'Exclusion',
    'warning': 'Avertissement',
    'rule_change': 'Changement de règle',
    'content_removal': 'Suppression de contenu',
    'dispute': 'Résolution de conflit',
    'other': 'Autre',
}


class GovernancePortal(CustomerPortal):

    def _prepare_home_portal_values(self, counters):
        values = super()._prepare_home_portal_values(counters)
        if 'proposals_voting_count' in counters:
            values['proposals_voting_count'] = request.env['social_governance.proposal'].sudo().search_count([
                ('state', '=', 'voting'),
            ])
        return values

    @route('/governance', auth='user', website=True, sitemap=True)
    def governance_list(self, page=1, state='voting', **kw):
        Proposal = request.env['social_governance.proposal'].sudo()
        valid_states = list(_STATE_LABELS.keys())
        if state not in valid_states:
            state = 'voting'
        domain = [('state', '=', state)] if state != 'all' else []
        total = Proposal.search_count(domain)
        pager = portal_pager(
            url='/governance', url_args={'state': state},
            total=total, page=page, step=10,
        )
        proposals = Proposal.search(domain, order='create_date desc', limit=10, offset=pager['offset'])
        return request.render('social_governance.portal_governance_list', {
            'proposals': proposals,
            'pager': pager,
            'state_filter': state,
            'state_labels': _STATE_LABELS,
            'page_name': 'governance',
        })

    @route('/governance/<int:proposal_id>', auth='user', website=True)
    def governance_detail(self, proposal_id, **kw):
        proposal = request.env['social_governance.proposal'].sudo().browse(proposal_id).exists()
        if not proposal:
            raise NotFound()
        my_vote = proposal.vote_ids.filtered(lambda v: v.voter_id == request.env.user)
        return request.render('social_governance.portal_governance_detail', {
            'proposal': proposal,
            'my_vote': my_vote[:1].choice if my_vote else False,
            'state_labels': _STATE_LABELS,
            'page_name': 'governance',
        })

    @route('/governance/<int:proposal_id>/vote', auth='user', methods=['POST'], website=True, csrf=True)
    def governance_vote(self, proposal_id, choice='abstain', **kw):
        proposal = request.env['social_governance.proposal'].sudo().browse(proposal_id).exists()
        if not proposal or proposal.state != 'voting':
            raise NotFound()
        if choice not in ('yes', 'no', 'abstain'):
            return request.redirect('/governance/%d?error=invalid_choice' % proposal_id)
        proposal.with_user(request.env.user).action_vote(choice)
        return request.redirect('/governance/%d?voted=1' % proposal_id)

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
            'category_labels': _CATEGORY_LABELS,
            'page_name': 'governance',
        })
