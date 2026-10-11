from odoo import http, _
from odoo.http import request
from odoo.exceptions import UserError, ValidationError


class ConsentPortalController(http.Controller):

    @http.route('/consent/gate/<int:gate_id>', auth='user', website=True)
    def view_gate(self, gate_id, **kw):
        gate = request.env['social_consent.gate'].browse(gate_id)
        if not gate.exists() or not gate.is_active:
            return request.not_found()

        existing_req = request.env['social_consent.request'].search([
            ('gate_id', '=', gate.id),
            ('requester_id', '=', request.env.user.id),
            ('state', 'in', ('draft', 'submitted', 'under_review', 'approved')),
        ], limit=1, order='id desc')

        return request.render('social_consent.portal_gate', {
            'gate': gate,
            'existing_request': existing_req,
        })

    @http.route('/consent/gate/<int:gate_id>/start', auth='user', methods=['POST'], website=True, csrf=True)
    def start_request(self, gate_id, **post):
        gate = request.env['social_consent.gate'].browse(gate_id)
        if not gate.exists() or not gate.is_active:
            return request.not_found()

        try:
            req = request.env['social_consent.request'].create({
                'gate_id': gate.id,
                'requester_id': request.env.user.id,
            })
            for item in gate.item_ids:
                key_check = f'check_{item.id}'
                key_text = f'text_{item.id}'
                request.env['social_consent.answer'].create({
                    'request_id': req.id,
                    'item_id': item.id,
                    'checked': bool(post.get(key_check)),
                    'text': post.get(key_text, '').strip() or False,
                })
            req.action_submit()
        except (UserError, ValidationError) as e:
            return request.render('social_consent.portal_gate', {
                'gate': gate,
                'error': str(e),
            })

        return request.redirect(f'/consent/request/{req.id}')

    @http.route('/consent/request/<int:req_id>', auth='user', website=True)
    def view_request(self, req_id, **kw):
        req = request.env['social_consent.request'].sudo().browse(req_id)
        if not req.exists():
            return request.not_found()
        user = request.env.user
        if req.requester_id != user and req.gate_id.profile_id.user_id != user:
            return request.not_found()
        return request.render('social_consent.portal_request', {'req': req})

    @http.route('/consent/request/<int:req_id>/approve', auth='user', methods=['POST'], website=True, csrf=True)
    def approve_request(self, req_id, note='', **kw):
        req = request.env['social_consent.request'].browse(req_id)
        if not req.exists():
            return request.not_found()
        try:
            req.action_approve(note=note or None)
        except (UserError, ValidationError) as e:
            return request.render('social_consent.portal_request', {'req': req, 'error': str(e)})
        return request.redirect(f'/consent/request/{req_id}')

    @http.route('/consent/request/<int:req_id>/reject', auth='user', methods=['POST'], website=True, csrf=True)
    def reject_request(self, req_id, note='', **kw):
        req = request.env['social_consent.request'].browse(req_id)
        if not req.exists():
            return request.not_found()
        try:
            req.action_reject(note=note or None)
        except (UserError, ValidationError) as e:
            return request.render('social_consent.portal_request', {'req': req, 'error': str(e)})
        return request.redirect(f'/consent/request/{req_id}')

    @http.route('/consent/request/<int:req_id>/withdraw', auth='user', methods=['POST'], website=True, csrf=True)
    def withdraw_request(self, req_id, **kw):
        req = request.env['social_consent.request'].browse(req_id)
        if not req.exists():
            return request.not_found()
        try:
            req.action_withdraw()
        except (UserError, ValidationError) as e:
            return request.render('social_consent.portal_request', {'req': req, 'error': str(e)})
        return request.redirect(f'/consent/request/{req_id}')
