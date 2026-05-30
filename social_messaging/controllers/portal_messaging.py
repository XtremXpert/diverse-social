import base64
import json
import logging

from odoo import _, http
from odoo.exceptions import UserError, ValidationError
from odoo.http import request, route

from odoo.addons.portal.controllers.portal import CustomerPortal

_logger = logging.getLogger(__name__)

_ALLOWED_EMOJIS = {'👍', '❤️', '😂', '😮', '😢', '👏'}
_MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024  # 10 MB per file
_MAX_ATTACHMENTS = 10


class MessagingPortal(CustomerPortal):

    # ── Thread list ───────────────────────────────────────────────────────

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

    # ── Single thread view ────────────────────────────────────────────────

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

    # ── Start a conversation ──────────────────────────────────────────────

    @route('/my/messages/start/<int:user_id>', auth='user', website=True, methods=['POST'], csrf=True)
    def messages_start(self, user_id, **kw):
        user = request.env.user
        if user_id == user.id:
            return request.redirect('/my/messages')
        try:
            with request.env.cr.savepoint():
                thread = request.env['social_messaging.thread'].sudo()._get_or_create(
                    [user.id, user_id]
                )
        except UserError:
            return request.redirect('/my/messages')
        return request.redirect(f'/my/messages/{thread.id}')

    # ── Send message (AJAX, multipart) ────────────────────────────────────

    @route('/my/messages/<int:thread_id>/send', auth='user', website=True, methods=['POST'], csrf=True)
    def messages_send(self, thread_id, content='', **kw):
        user = request.env.user
        thread = request.env['social_messaging.thread'].sudo().browse(thread_id)
        if not thread.exists() or user not in thread.participant_ids:
            return self._json_error(_('Thread not found'), 404)

        content = (content or '').strip()

        # Collect files (repeated `attachments` field, multipart/form-data).
        files = request.httprequest.files.getlist('attachments') or []
        if len(files) > _MAX_ATTACHMENTS:
            return self._json_error(
                _('Too many attachments (max %s).') % _MAX_ATTACHMENTS, 200)

        if not content and not files:
            return self._json_error(_('Empty message'), 200)

        try:
            msg = request.env['social_messaging.message'].sudo().create({
                'thread_id': thread_id,
                'author_id': user.id,
                'content': content or False,
                'read_by_ids': [(4, user.id)],
            })
            for f in files:
                if not f or not f.filename:
                    continue
                data = f.read()
                if not data:
                    continue
                if len(data) > _MAX_ATTACHMENT_BYTES:
                    raise UserError(
                        _('File "%s" is too large (max 10 MB).') % f.filename)
                request.env['ir.attachment'].sudo().create({
                    'name': f.filename,
                    'datas': base64.b64encode(data),
                    'res_model': 'social_messaging.message',
                    'res_id': msg.id,
                    'mimetype': f.mimetype or 'application/octet-stream',
                })
            # Single broadcast after the message is complete (attachments
            # created). The model does not broadcast in create() precisely
            # to avoid emitting an intermediate notification without files.
            msg._broadcast('message_new')
        except (UserError, ValidationError) as e:
            return self._json_error(str(e), 200)
        except Exception:
            _logger.exception('Error sending message')
            return self._json_error(_('Internal error'), 500)

        return request.make_response(
            json.dumps({'ok': True, 'message': self._msg_dict(msg, user)}),
            headers=[('Content-Type', 'application/json')],
        )

    # ── Reaction (toggle emoji) ───────────────────────────────────────────

    @route('/my/messages/<int:thread_id>/react', auth='user', website=True, methods=['POST'], csrf=True)
    def messages_react(self, thread_id, message_id=0, emoji='', **kw):
        user = request.env.user
        thread = request.env['social_messaging.thread'].sudo().browse(thread_id)
        if not thread.exists() or user not in thread.participant_ids:
            return self._json_error(_('Thread not found'), 404)

        emoji = (emoji or '').strip()
        if emoji not in _ALLOWED_EMOJIS:
            return self._json_error(_('Emoji not allowed'), 200)

        msg = request.env['social_messaging.message'].sudo().browse(int(message_id or 0))
        if not msg.exists() or msg.thread_id.id != thread.id:
            return self._json_error(_('Message not found'), 404)

        try:
            action, _rec = request.env['social_messaging.reaction'].toggle(msg.id, emoji)
        except (UserError, ValidationError) as e:
            return self._json_error(str(e), 200)

        return request.make_response(
            json.dumps({
                'ok': True,
                'action': action,
                'message': self._msg_dict(msg, user),
            }),
            headers=[('Content-Type', 'application/json')],
        )

    # ── Fetch a single message (used by the OWL frontend on bus events) ───

    @route('/my/messages/<int:thread_id>/message/<int:message_id>', auth='user', website=True, methods=['GET'], csrf=False)
    def message_fetch(self, thread_id, message_id, **kw):
        user = request.env.user
        thread = request.env['social_messaging.thread'].sudo().browse(thread_id)
        if not thread.exists() or user not in thread.participant_ids:
            return self._json_error(_('Thread not found'), 404)
        msg = request.env['social_messaging.message'].sudo().browse(int(message_id))
        if not msg.exists() or msg.thread_id.id != thread.id:
            return self._json_error(_('Message not found'), 404)
        return request.make_response(
            json.dumps({'ok': True, 'message': self._msg_dict(msg, user)}),
            headers=[('Content-Type', 'application/json')],
        )

    # ── Polling fallback (used when websockets are unavailable) ───────────

    @route('/my/messages/<int:thread_id>/poll', auth='user', website=True, methods=['GET'], csrf=False)
    def messages_poll(self, thread_id, since_id=0, **kw):
        user = request.env.user
        thread = request.env['social_messaging.thread'].sudo().browse(thread_id)
        if not thread.exists() or user not in thread.participant_ids:
            return self._json_error(_('Thread not found'), 404)

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
        # Attachments: public URL /web/content, is_image flag for inline render.
        attachments = []
        for att in msg.attachment_ids.sudo():
            mimetype = att.mimetype or 'application/octet-stream'
            attachments.append({
                'id': att.id,
                'name': att.name or '',
                'mimetype': mimetype,
                'is_image': mimetype.startswith('image/'),
                'url': f'/web/content/{att.id}?download=0',
                'download_url': f'/web/content/{att.id}?download=1',
            })
        # Reactions grouped by emoji.
        reactions_grouped = {}
        for r in msg.reaction_ids.sudo():
            slot = reactions_grouped.setdefault(r.emoji, {'emoji': r.emoji, 'count': 0, 'user_ids': []})
            slot['count'] += 1
            slot['user_ids'].append(r.user_id.id)
        return {
            'id': msg.id,
            'author_id': msg.author_id.id,
            'author_name': msg.author_id.name,
            'content': msg.content or '',
            'is_mine': msg.author_id.id == user.id,
            'create_date': msg.create_date.strftime('%d/%m/%Y %H:%M') if msg.create_date else '',
            'attachments': attachments,
            'reactions': list(reactions_grouped.values()),
        }

    def _json_error(self, msg, status=400):
        return request.make_response(
            json.dumps({'ok': False, 'error': msg}),
            status=status,
            headers=[('Content-Type', 'application/json')],
        )
