import json
import logging

from odoo import http
from odoo.exceptions import UserError
from odoo.http import request, route

from odoo.addons.portal.controllers.portal import CustomerPortal

_logger = logging.getLogger(__name__)


class MessagingPortal(CustomerPortal):

    # ── Liste des fils ────────────────────────────────────────────────────

    @route('/my/messages', auth='user', website=True, sitemap=False)
    def messages_list(self, **kw):
        user = request.env.user
        threads = request.env['social_messaging.thread'].sudo().search(
            [('participant_ids', 'in', [user.id])],
            order='last_message_date desc',
        )
        thread_data = []
        for t in threads:
            other = t.other_participant(user)
            other_profile = None
            if other:
                other_profile = request.env['club_social_profile.profile'].sudo().search(
                    [('user_id', '=', other.id)], limit=1
                )
            thread_data.append({
                'thread': t,
                'other': other,
                'other_profile': other_profile,
                'unread': t.unread_count_for(user),
            })
        return request.render('social_messaging.portal_messages_list', {
            'thread_data': thread_data,
            'page_name': 'messages',
        })

    # ── Fil de discussion ─────────────────────────────────────────────────

    @route('/my/messages/<int:thread_id>', auth='user', website=True, sitemap=False)
    def messages_thread(self, thread_id, **kw):
        user = request.env.user
        thread = request.env['social_messaging.thread'].sudo().browse(thread_id)
        if not thread.exists() or user not in thread.participant_ids:
            return request.not_found()

        other = thread.other_participant(user)
        other_profile = None
        if other:
            other_profile = request.env['club_social_profile.profile'].sudo().search(
                [('user_id', '=', other.id)], limit=1
            )

        messages = thread.message_ids.sorted('id')
        unread = messages.filtered(
            lambda m: m.author_id != user and user not in m.read_by_ids
        )
        if unread:
            unread.mark_as_read(user)

        return request.render('social_messaging.portal_messages_thread', {
            'thread': thread,
            'messages': messages,
            'other': other,
            'other_profile': other_profile,
            'last_message_id': messages[-1].id if messages else 0,
            'page_name': 'messages',
        })

    # ── Démarrer une conversation ─────────────────────────────────────────

    @route('/my/messages/start/<int:user_id>', auth='user', website=True, methods=['POST'], csrf=True)
    def messages_start(self, user_id, **kw):
        user = request.env.user
        if user_id == user.id:
            return request.redirect('/my/messages')
        try:
            thread = request.env['social_messaging.thread'].sudo()._get_or_create(
                [user.id, user_id]
            )
            return request.redirect(f'/my/messages/{thread.id}')
        except UserError:
            return request.redirect('/my/messages')

    # ── Envoi de message (AJAX) ───────────────────────────────────────────

    @route('/my/messages/<int:thread_id>/send', auth='user', website=True, methods=['POST'], csrf=True)
    def messages_send(self, thread_id, content='', **kw):
        user = request.env.user
        thread = request.env['social_messaging.thread'].sudo().browse(thread_id)
        if not thread.exists() or user not in thread.participant_ids:
            return self._json_error('Thread introuvable', 404)

        content = (content or '').strip()
        if not content:
            return self._json_error('Message vide', 200)

        try:
            msg = request.env['social_messaging.message'].sudo().create({
                'thread_id': thread_id,
                'author_id': user.id,
                'content': content,
                'read_by_ids': [(4, user.id)],
            })
        except (UserError, Exception) as e:
            return self._json_error(str(e), 200)

        return request.make_response(
            json.dumps({'ok': True, 'message': self._msg_dict(msg, user)}),
            headers=[('Content-Type', 'application/json')],
        )

    # ── Polling des nouveaux messages ─────────────────────────────────────

    @route('/my/messages/<int:thread_id>/poll', auth='user', website=True, methods=['GET'], csrf=False)
    def messages_poll(self, thread_id, since_id=0, **kw):
        user = request.env.user
        thread = request.env['social_messaging.thread'].sudo().browse(thread_id)
        if not thread.exists() or user not in thread.participant_ids:
            return self._json_error('Thread introuvable', 404)

        new_msgs = thread.message_ids.filtered(lambda m: m.id > int(since_id)).sorted('id')
        unread = new_msgs.filtered(
            lambda m: m.author_id != user and user not in m.read_by_ids
        )
        if unread:
            unread.mark_as_read(user)

        return request.make_response(
            json.dumps({'ok': True, 'messages': [self._msg_dict(m, user) for m in new_msgs]}),
            headers=[('Content-Type', 'application/json')],
        )

    # ── Helpers ──────────────────────────────────────────────────────────

    def _msg_dict(self, msg, user):
        return {
            'id': msg.id,
            'author_id': msg.author_id.id,
            'author_name': msg.author_id.name,
            'content': msg.content,
            'is_mine': msg.author_id.id == user.id,
            'create_date': msg.create_date.strftime('%d/%m/%Y %H:%M') if msg.create_date else '',
        }

    def _json_error(self, msg, status=400):
        return request.make_response(
            json.dumps({'ok': False, 'error': msg}),
            status=status,
            headers=[('Content-Type', 'application/json')],
        )
