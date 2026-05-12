import logging

from odoo import http
from odoo.http import request
from odoo.exceptions import AccessError

from odoo.addons.social_base.controllers.mixins import SocialBaseMixin

_logger = logging.getLogger(__name__)


class SocialMessagingAPI(SocialBaseMixin, http.Controller):

    @http.route('/social/api/messages/thread', type='http', auth='user', methods=['POST'], csrf=False)
    def api_get_or_create_thread(self, **kwargs):
        try:
            user = self._validate_auth()
            body = self._get_json_body()
            recipient_id = body.get('recipient_id') or kwargs.get('recipient_id')
            if not recipient_id:
                return self._error_response('recipient_id required', 'INVALID_INPUT')

            thread = request.env['social_messaging.thread'].sudo()._get_or_create(
                [user.id, int(recipient_id)]
            )
            return self._success_response(self._thread_to_dict(thread, user))

        except AccessError as e:
            return self._error_response(str(e), 'AUTH_ERROR', 401)
        except Exception:
            _logger.exception('Error getting thread')
            return self._error_response('Internal error', 'THREAD_ERROR')

    @http.route('/social/api/messages/threads', type='http', auth='user', methods=['GET'], csrf=False)
    def api_list_threads(self, **kwargs):
        try:
            user = self._validate_auth()
            threads = request.env['social_messaging.thread'].sudo().search(
                [('participant_ids', 'in', [user.id])],
                order='last_message_date desc',
            )
            return self._success_response({
                'threads': [self._thread_to_dict(t, user) for t in threads],
            })

        except AccessError as e:
            return self._error_response(str(e), 'AUTH_ERROR', 401)
        except Exception:
            _logger.exception('Error listing threads')
            return self._error_response('Internal error', 'LIST_ERROR')

    @http.route('/social/api/messages/threads/<int:thread_id>/messages', type='http', auth='user', methods=['GET'], csrf=False)
    def api_list_messages(self, thread_id, limit=50, offset=0, **kwargs):
        try:
            user = self._validate_auth()
            thread = request.env['social_messaging.thread'].sudo().browse(thread_id)
            if not thread.exists() or user not in thread.participant_ids:
                return self._error_response('Thread not found', 'NOT_FOUND', 404)

            messages = thread.message_ids.sorted('id')[int(offset):int(offset) + int(limit)]
            return self._success_response({
                'messages': [self._message_to_dict(m) for m in messages],
                'total': len(thread.message_ids),
            })

        except AccessError as e:
            return self._error_response(str(e), 'AUTH_ERROR', 401)
        except Exception:
            _logger.exception('Error listing messages')
            return self._error_response('Internal error', 'LIST_ERROR')

    @http.route('/social/api/messages/threads/<int:thread_id>/messages', type='http', auth='user', methods=['POST'], csrf=False)
    def api_send_message(self, thread_id, **kwargs):
        try:
            user = self._validate_auth()
            thread = request.env['social_messaging.thread'].sudo().browse(thread_id)
            if not thread.exists() or user not in thread.participant_ids:
                return self._error_response('Thread not found', 'NOT_FOUND', 404)

            body = self._get_json_body()
            content = body.get('content') or kwargs.get('content')
            if not content or not content.strip():
                return self._error_response('Content required', 'INVALID_INPUT')

            msg = request.env['social_messaging.message'].sudo().create({
                'thread_id': thread_id,
                'author_id': user.id,
                'content': content,
                'read_by_ids': [(4, user.id)],
            })
            return self._success_response(self._message_to_dict(msg))

        except AccessError as e:
            return self._error_response(str(e), 'AUTH_ERROR', 401)
        except Exception:
            _logger.exception('Error sending message')
            return self._error_response('Internal error', 'SEND_ERROR')

    @http.route('/social/api/messages/<int:message_id>/read', type='http', auth='user', methods=['POST'], csrf=False)
    def api_mark_read(self, message_id, **kwargs):
        try:
            user = self._validate_auth()
            msg = request.env['social_messaging.message'].sudo().browse(message_id)
            if not msg.exists() or user not in msg.thread_id.participant_ids:
                return self._error_response('Message not found', 'NOT_FOUND', 404)

            msg.mark_as_read(user)
            return self._success_response({'read': True})

        except AccessError as e:
            return self._error_response(str(e), 'AUTH_ERROR', 401)
        except Exception:
            _logger.exception('Error marking read')
            return self._error_response('Internal error', 'READ_ERROR')

    def _thread_to_dict(self, thread, user):
        other = thread.other_participant(user)
        return {
            'id': thread.id,
            'other_participant': {'id': other.id, 'name': other.name} if other else None,
            'last_message_date': thread.last_message_date.isoformat() if thread.last_message_date else None,
            'last_message_preview': thread.last_message_preview,
            'unread_count': thread.unread_count_for(user),
        }

    def _message_to_dict(self, msg):
        return {
            'id': msg.id,
            'author': {'id': msg.author_id.id, 'name': msg.author_id.name},
            'content': msg.content,
            'create_date': msg.create_date.isoformat() if msg.create_date else None,
            'read_by_ids': msg.read_by_ids.ids,
        }
