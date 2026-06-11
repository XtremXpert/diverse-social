from datetime import datetime, timedelta
from urllib.parse import quote

from werkzeug.exceptions import Forbidden, NotFound

from odoo import _, fields
from odoo.exceptions import UserError
from odoo.http import request, route
from odoo.addons.portal.controllers.portal import CustomerPortal, pager as portal_pager


def _redirect_error(proposal_id, exc):
    # quote so multi-line ORM error messages don't break the Location header.
    return request.redirect(f'/governance/{proposal_id}?error={quote(str(exc), safe="")}')


def _state_labels():
    return {
        'draft': _('Draft'),
        'open': _('Open'),
        'voting': _('Voting'),
        'accepted': _('Accepted'),
        'rejected': _('Rejected'),
        'inconclusive': _('Inconclusive (quorum)'),
        'withdrawn': _('Withdrawn'),
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

    @route(['/governance', '/governance/page/<int:page>'], auth='user', website=True, sitemap=True)
    def governance_list(self, page=1, state='voting', **kw):
        Proposal = request.env['social_governance.proposal'].sudo()
        valid_states = list(_state_labels().keys())
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
            'state_labels': _state_labels(),
            'categories': categories,
            'page_name': 'governance',
            'error': kw.get('error'),
        })

    # ── Create a proposal ──────────────────────────────────────────────────────

    @route('/governance/create', auth='user', methods=['GET', 'POST'], website=True, csrf=True)
    def governance_create(self, name='', description='', category_id='',
                          voting_closes_at='', **kw):
        if request.httprequest.method == 'GET':
            return request.redirect('/governance')
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
                closes = datetime.fromisoformat(voting_closes_at.replace('T', ' '))
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

    # ── Detail ─────────────────────────────────────────────────────────────────

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
            'state_labels': _state_labels(),
            'is_author': is_author,
            'is_moderator': is_moderator,
            'deadline_hours': deadline_hours,
            'page_name': 'governance',
            'error': kw.get('error'),
        })

    # ── Vote ───────────────────────────────────────────────────────────────────

    @route('/governance/<int:proposal_id>/vote', auth='user', methods=['POST'],
           website=True, csrf=True)
    def governance_vote(self, proposal_id, choice='abstain', **kw):
        proposal = request.env['social_governance.proposal'].sudo().browse(proposal_id).exists()
        if not proposal or proposal.state != 'voting':
            raise NotFound()
        if choice not in ('yes', 'no', 'abstain'):
            return request.redirect(f'/governance/{proposal_id}?error=invalid_choice')
        try:
            with request.env.cr.savepoint():
                proposal.with_user(request.env.user).action_vote(choice)
        except UserError as e:
            return _redirect_error(proposal_id, e)
        return request.redirect(f'/governance/{proposal_id}?voted=1')

    # ── Open a proposal ────────────────────────────────────────────────────────

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
            with request.env.cr.savepoint():
                proposal.with_user(user).action_open()
        except UserError as e:
            return _redirect_error(proposal_id, e)
        return request.redirect(f'/governance/{proposal_id}?opened=1')

    # ── Start voting ───────────────────────────────────────────────────────────

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
                closes = datetime.fromisoformat(voting_closes_at.replace('T', ' '))
                proposal.sudo().write({'voting_closes_at': closes})
            except Exception:
                return request.redirect(f'/governance/{proposal_id}?error=invalid_date')
        try:
            with request.env.cr.savepoint():
                proposal.with_user(user).action_start_voting()
        except UserError as e:
            return _redirect_error(proposal_id, e)
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
            with request.env.cr.savepoint():
                proposal.with_user(user).action_withdraw()
        except UserError as e:
            return _redirect_error(proposal_id, e)
        return request.redirect(f'/governance/{proposal_id}?withdrawn=1')

    # ── Decisions log ──────────────────────────────────────────────────────────

    @route(['/governance/log', '/governance/log/page/<int:page>'], auth='user', website=True, sitemap=True)
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
