from werkzeug.exceptions import Forbidden, NotFound

from odoo import _
from odoo.exceptions import UserError
from odoo.http import request, route
from odoo.addons.portal.controllers.portal import CustomerPortal, pager as portal_pager

_STATES = {
    'draft': 'Brouillon',
    'shared': 'Partagé',
    'reviewing': 'En révision',
    'active': 'Actif',
    'archived': 'Archivé',
}

_VALID_RESPONSE = frozenset({'oui', 'soft', 'non', 'na', ''})
_VALID_CATEGORY = frozenset({'hard_limit', 'soft_limit', 'desire', 'safeguard', 'other'})

_CAT_LABELS = {
    'hard_limit': 'Limites dures',
    'soft_limit': 'Limites douces',
    'desire': 'Désirs',
    'safeguard': 'Safeguards / Aftercare',
    'other': 'Autre',
}

_RESP_LABELS = {
    'oui': '✅ Oui',
    'soft': '🟡 Peut-être / Soft',
    'non': '🚫 Non / Hard limit',
    'na': '— N/A',
}


class NegotiationPortal(CustomerPortal):

    def _prepare_portal_counter_values(self, counter):
        if counter == 'negotiation_count':
            user = request.env.user
            return 'social_negotiation.negotiation', [
                '|', ('initiator_id', '=', user.id), ('partner_id', '=', user.id),
                ('state', 'not in', ['archived']),
            ], 'read'
        return super()._prepare_portal_counter_values(counter)

    # ── Liste ─────────────────────────────────────────────────────────────

    @route('/my/negotiation', auth='user', website=True)
    def my_negotiations(self, page=1, state='all', **kw):
        user = request.env.user
        domain = ['|', ('initiator_id', '=', user.id), ('partner_id', '=', user.id)]
        if state != 'all':
            domain.append(('state', '=', state))
        total = request.env['social_negotiation.negotiation'].search_count(domain)
        pager = portal_pager(
            url='/my/negotiation', url_args={'state': state},
            total=total, page=int(page), step=10,
        )
        negotiations = request.env['social_negotiation.negotiation'].search(
            domain, order='id desc', limit=10, offset=pager['offset']
        )
        connections = _get_user_connections(user)
        return request.render('social_negotiation.portal_my_negotiations', {
            'negotiations': negotiations,
            'pager': pager,
            'state_filter': state,
            'state_labels': _STATES,
            'connections': connections,
            'page_name': 'negotiation',
        })

    # ── Créer ──────────────────────────────────────────────────────────────

    @route('/my/negotiation/create', auth='user', methods=['POST'], website=True, csrf=True)
    def negotiation_create(self, partner_id='', safe_word='', **kw):
        user = request.env.user
        if not partner_id:
            return request.redirect('/my/negotiation?error=partner_required')
        try:
            pid = int(partner_id)
        except (ValueError, TypeError):
            return request.redirect('/my/negotiation?error=partner_required')

        connections = _get_user_connections(user)
        partner = request.env['res.users'].sudo().browse(pid)
        if not partner.exists() or partner not in connections:
            return request.redirect('/my/negotiation?error=not_connected')

        neg = request.env['social_negotiation.negotiation'].sudo().create({
            'initiator_id': user.id,
            'partner_id': pid,
            'safe_word': (safe_word or '').strip() or False,
        })
        return request.redirect(f'/my/negotiation/{neg.id}')

    # ── Détail ─────────────────────────────────────────────────────────────

    @route('/my/negotiation/<int:neg_id>', auth='user', website=True)
    def negotiation_detail(self, neg_id, **kw):
        neg, user = _load_neg(neg_id)
        items_by_category = {}
        for item in neg.item_ids.sorted(key=lambda i: (i.category, i.sequence)):
            items_by_category.setdefault(item.category, []).append(item)
        return request.render('social_negotiation.portal_negotiation_detail', {
            'neg': neg,
            'items_by_category': items_by_category,
            'state_labels': _STATES,
            'category_labels': _CAT_LABELS,
            'response_labels': _RESP_LABELS,
            'is_initiator': user == neg.initiator_id,
            'user_signed': _user_signed(neg, user),
            'page_name': 'negotiation',
        })

    # ── Ajouter un item ────────────────────────────────────────────────────

    @route('/my/negotiation/<int:neg_id>/item/add', auth='user', methods=['POST'],
           website=True, csrf=True)
    def negotiation_item_add(self, neg_id, text='', category='desire', **kw):
        neg, user = _load_neg(neg_id)
        if user != neg.initiator_id or neg.state != 'draft':
            raise Forbidden()
        text = (text or '').strip()
        if not text:
            return request.redirect(f'/my/negotiation/{neg_id}?error=item_empty')
        if category not in _VALID_CATEGORY:
            category = 'desire'
        request.env['social_negotiation.item'].sudo().create({
            'negotiation_id': neg_id,
            'text': text,
            'category': category,
        })
        return request.redirect(f'/my/negotiation/{neg_id}')

    # ── Supprimer un item ──────────────────────────────────────────────────

    @route('/my/negotiation/<int:neg_id>/item/<int:item_id>/delete', auth='user',
           methods=['POST'], website=True, csrf=True)
    def negotiation_item_delete(self, neg_id, item_id, **kw):
        neg, user = _load_neg(neg_id)
        if user != neg.initiator_id or neg.state != 'draft':
            raise Forbidden()
        item = request.env['social_negotiation.item'].sudo().browse(item_id)
        if item.exists() and item.negotiation_id.id == neg_id:
            item.unlink()
        return request.redirect(f'/my/negotiation/{neg_id}')

    # ── Remplir ses réponses ───────────────────────────────────────────────

    @route('/my/negotiation/<int:neg_id>/respond', auth='user', methods=['POST'],
           website=True, csrf=True)
    def negotiation_respond(self, neg_id, **kw):
        neg, user = _load_neg(neg_id)
        if neg.state not in ('shared', 'reviewing'):
            raise Forbidden()
        is_initiator = (user == neg.initiator_id)
        form = request.httprequest.form
        for item in neg.item_ids:
            key = f'response_{item.id}'
            val = form.get(key, '').strip()
            if val not in _VALID_RESPONSE:
                continue
            field = 'initiator_response' if is_initiator else 'partner_response'
            item.sudo().write({field: val or False})
        note_key_prefix = 'note_'
        for key, val in form.items():
            if not key.startswith(note_key_prefix):
                continue
            try:
                item_id = int(key[len(note_key_prefix):])
            except ValueError:
                continue
            item = request.env['social_negotiation.item'].sudo().browse(item_id)
            if item.exists() and item.negotiation_id.id == neg_id:
                item.sudo().write({'note': val.strip() or False})
        if neg.state == 'shared':
            try:
                with request.env.cr.savepoint():
                    neg.sudo().action_start_review()
            except UserError:
                pass
        return request.redirect(f'/my/negotiation/{neg_id}?responded=1')

    # ── Partager ───────────────────────────────────────────────────────────

    @route('/my/negotiation/<int:neg_id>/share', auth='user', methods=['POST'],
           website=True, csrf=True)
    def negotiation_share(self, neg_id, **kw):
        neg, user = _load_neg(neg_id)
        if user != neg.initiator_id:
            raise Forbidden()
        try:
            with request.env.cr.savepoint():
                neg.action_share()
        except UserError as e:
            return request.redirect(f'/my/negotiation/{neg_id}?error={e}')
        return request.redirect(f'/my/negotiation/{neg_id}')

    # ── Signer ─────────────────────────────────────────────────────────────

    @route('/my/negotiation/<int:neg_id>/sign', auth='user', methods=['POST'],
           website=True, csrf=True)
    def negotiation_sign(self, neg_id, **kw):
        neg, user = _load_neg(neg_id)
        try:
            with request.env.cr.savepoint():
                neg.action_sign()
        except UserError as e:
            return request.redirect(f'/my/negotiation/{neg_id}?error={e}')
        return request.redirect(f'/my/negotiation/{neg_id}')

    # ── Archiver ───────────────────────────────────────────────────────────

    @route('/my/negotiation/<int:neg_id>/archive', auth='user', methods=['POST'],
           website=True, csrf=True)
    def negotiation_archive(self, neg_id, **kw):
        neg, user = _load_neg(neg_id)
        try:
            with request.env.cr.savepoint():
                neg.action_archive()
        except UserError as e:
            return request.redirect(f'/my/negotiation/{neg_id}?error={e}')
        return request.redirect('/my/negotiation')

    # ── Nouvelle version ───────────────────────────────────────────────────

    @route('/my/negotiation/<int:neg_id>/new_version', auth='user', methods=['POST'],
           website=True, csrf=True)
    def negotiation_new_version(self, neg_id, **kw):
        neg, user = _load_neg(neg_id)
        try:
            with request.env.cr.savepoint():
                src = request.env['social_negotiation.negotiation'].sudo().browse(neg_id)
                new_neg = src.copy({
                    'state': 'draft',
                    'version': neg.version + 1,
                    'initiator_signed_at': False,
                    'partner_signed_at': False,
                    'archived_at': False,
                })
                for item in neg.item_ids:
                    item.copy({'negotiation_id': new_neg.id})
                neg.sudo().action_archive()
        except UserError as e:
            return request.redirect(f'/my/negotiation/{neg_id}?error={e}')
        return request.redirect(f'/my/negotiation/{new_neg.id}')


# ── Helpers module-level ─────────────────────────────────────────────────────

def _load_neg(neg_id):
    neg = request.env['social_negotiation.negotiation'].browse(neg_id).exists()
    user = request.env.user
    if not neg or user not in (neg.initiator_id, neg.partner_id):
        raise NotFound()
    return neg, user


def _user_signed(neg, user):
    if user == neg.initiator_id:
        return bool(neg.initiator_signed_at)
    return bool(neg.partner_signed_at)


def _get_user_connections(user):
    Connection = request.env['club_social_profile.connection'].sudo()
    sent = Connection.search([('user_id', '=', user.id), ('state', '=', 'accepted')])
    recv = Connection.search([('connected_user_id', '=', user.id), ('state', '=', 'accepted')])
    user_ids = set(sent.mapped('connected_user_id.id')) | set(recv.mapped('user_id.id'))
    if not user_ids:
        return request.env['res.users'].sudo().browse()
    return request.env['res.users'].sudo().browse(list(user_ids))
