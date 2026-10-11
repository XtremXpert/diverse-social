from werkzeug.exceptions import Forbidden, NotFound

from odoo import _
from odoo.exceptions import UserError, ValidationError
from odoo.http import request, route
from odoo.addons.portal.controllers.portal import CustomerPortal, pager as portal_pager


class ConsentMyPortal(CustomerPortal):

    # ── Compteur portail home ─────────────────────────────────────────────────

    def _prepare_portal_counter_values(self, counter):
        if counter == 'consent_count':
            gate = self._get_my_gate()
            if not gate:
                return False, [], False
            return 'social_consent.request', [
                ('gate_id', '=', gate.id),
                ('state', 'in', ('submitted', 'under_review')),
            ], 'read'
        return super()._prepare_portal_counter_values(counter)

    # ── Dashboard /my/consent ─────────────────────────────────────────────────

    @route('/my/consent', auth='user', website=True)
    def my_consent_home(self, **kw):
        gate = self._get_my_gate()
        pending_requests = (
            request.env['social_consent.request'].search([
                ('gate_id', '=', gate.id),
                ('state', 'in', ('submitted', 'under_review')),
            ], order='submitted_at asc') if gate else request.env['social_consent.request']
        )
        sent_requests = request.env['social_consent.request'].search([
            ('requester_id', '=', request.env.user.id),
        ], order='id desc', limit=5)

        return request.render('social_consent.portal_my_consent', {
            'gate': gate,
            'pending_requests': pending_requests,
            'sent_requests': sent_requests,
            'page_name': 'consent',
        })

    # ── Gestion de ma gate ────────────────────────────────────────────────────

    @route('/my/consent/gate', auth='user', website=True)
    def my_gate(self, **kw):
        gate = self._get_my_gate()
        return request.render('social_consent.portal_my_gate', {
            'gate': gate,
            'page_name': 'consent',
        })

    @route('/my/consent/gate/save', auth='user', methods=['POST'], website=True, csrf=True)
    def save_gate(self, intro_text='', min_delay_hours=24, require_all_checks='', **kw):
        gate = self._get_or_create_my_gate()
        try:
            try:
                delay = max(0, int(min_delay_hours or 0))
            except (ValueError, TypeError):
                delay = 0
            gate.write({
                'intro_text': intro_text.strip() or False,
                'min_delay_hours': delay,
                'require_all_checks': bool(require_all_checks),
            })
        except (UserError, ValidationError) as e:
            return request.render('social_consent.portal_my_gate', {
                'gate': gate,
                'error': str(e),
                'page_name': 'consent',
            })
        return request.redirect('/my/consent/gate')

    @route('/my/consent/gate/toggle', auth='user', methods=['POST'], website=True, csrf=True)
    def toggle_gate(self, **kw):
        gate = self._get_or_create_my_gate()
        gate.write({'is_active': not gate.is_active})
        return request.redirect('/my/consent/gate')

    @route('/my/consent/gate/item/add', auth='user', methods=['POST'], website=True, csrf=True)
    def add_gate_item(self, item_type='check', text='', required='', hint='', **kw):
        gate = self._get_or_create_my_gate()
        text = (text or '').strip()
        if not text:
            return request.render('social_consent.portal_my_gate', {
                'gate': gate,
                'error': _('Le texte de la condition est obligatoire.'),
                'page_name': 'consent',
            })
        if item_type not in ('check', 'question'):
            raise NotFound()
        try:
            request.env['social_consent.gate_item'].create({
                'gate_id': gate.id,
                'item_type': item_type,
                'text': text,
                'required': bool(required),
                'hint': (hint or '').strip() or False,
            })
        except (UserError, ValidationError) as e:
            return request.render('social_consent.portal_my_gate', {
                'gate': gate,
                'error': str(e),
                'page_name': 'consent',
            })
        return request.redirect('/my/consent/gate')

    @route('/my/consent/gate/item/<int:item_id>/delete', auth='user', methods=['POST'], website=True, csrf=True)
    def delete_gate_item(self, item_id, **kw):
        item = request.env['social_consent.gate_item'].browse(item_id).exists()
        if not item or item.gate_id.profile_id.user_id != request.env.user:
            raise Forbidden()
        item.unlink()
        return request.redirect('/my/consent/gate')

    # ── Received requests (full view) ─────────────────────────────────────────

    @route('/my/consent/received', auth='user', website=True)
    def received_requests(self, page=1, state='all', **kw):
        gate = self._get_my_gate()
        if not gate:
            return request.redirect('/my/consent')

        domain = [('gate_id', '=', gate.id)]
        if state != 'all':
            domain.append(('state', '=', state))

        total = request.env['social_consent.request'].search_count(domain)
        pager = portal_pager(url='/my/consent/received', url_args={'state': state},
                             total=total, page=page, step=10)
        reqs = request.env['social_consent.request'].search(
            domain, order='submitted_at desc', limit=10, offset=pager['offset']
        )
        return request.render('social_consent.portal_received_requests', {
            'gate': gate,
            'requests': reqs,
            'pager': pager,
            'state_filter': state,
            'page_name': 'consent',
        })

    # ── Sent requests (full view) ─────────────────────────────────────────────

    @route('/my/consent/sent', auth='user', website=True)
    def sent_requests(self, page=1, **kw):
        domain = [('requester_id', '=', request.env.user.id)]
        total = request.env['social_consent.request'].search_count(domain)
        pager = portal_pager(url='/my/consent/sent', total=total, page=page, step=10)
        reqs = request.env['social_consent.request'].search(
            domain, order='id desc', limit=10, offset=pager['offset']
        )
        return request.render('social_consent.portal_sent_requests', {
            'requests': reqs,
            'pager': pager,
            'page_name': 'consent',
        })

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _get_my_gate(self):
        """Retourne la gate de l'utilisateur courant, ou un recordset vide."""
        profile = request.env['club_social_profile.profile'].search(
            [('user_id', '=', request.env.user.id)], limit=1
        )
        if not profile:
            return request.env['social_consent.gate']
        return request.env['social_consent.gate'].search(
            [('profile_id', '=', profile.id)], limit=1
        )

    def _get_or_create_my_gate(self):
        """Return or create the current user's gate."""
        gate = self._get_my_gate()
        if gate:
            return gate
        Profile = request.env['club_social_profile.profile']
        profile = Profile.sudo().get_or_create_for_user(request.env.user)
        return request.env['social_consent.gate'].create({'profile_id': profile.id})
