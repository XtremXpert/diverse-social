import logging

from odoo import http
from odoo.http import request
from odoo.exceptions import AccessError

from odoo.addons.social_base.controllers.mixins import SocialBaseMixin

_logger = logging.getLogger(__name__)


class SocialGalleryAPI(SocialBaseMixin, http.Controller):

    @http.route('/social/api/galleries', type='http', auth='user', methods=['GET'], csrf=False)
    def api_list_galleries(self, owner_id=None, **kwargs):
        try:
            user = self._validate_auth()
            domain = []
            if owner_id:
                domain.append(('owner_id', '=', int(owner_id)))

            galleries = request.env['social_gallery.gallery'].sudo().search(domain, order='sequence, id')
            galleries = galleries.filtered(lambda g: g.is_accessible_by(user))
            return self._success_response({
                'galleries': [self._gallery_to_dict(g) for g in galleries],
            })

        except AccessError as e:
            return self._error_response(str(e), 'AUTH_ERROR', 401)
        except Exception:
            _logger.exception('Error listing galleries')
            return self._error_response('Internal error', 'LIST_ERROR')

    @http.route('/social/api/galleries/<int:gallery_id>/photos', type='http', auth='user', methods=['GET'], csrf=False)
    def api_list_photos(self, gallery_id, **kwargs):
        try:
            user = self._validate_auth()
            gallery = request.env['social_gallery.gallery'].sudo().browse(gallery_id)
            if not gallery.exists():
                return self._error_response('Gallery not found', 'NOT_FOUND', 404)
            if not gallery.is_accessible_by(user):
                return self._error_response('Access denied', 'FORBIDDEN', 403)

            photos = gallery.photo_ids.filtered(lambda p: p.state == 'approved')
            return self._success_response({
                'photos': [self._photo_to_dict(p) for p in photos],
                'total': len(photos),
            })

        except AccessError as e:
            return self._error_response(str(e), 'AUTH_ERROR', 401)
        except Exception:
            _logger.exception('Error listing photos')
            return self._error_response('Internal error', 'LIST_ERROR')

    @http.route('/social/api/galleries/<int:gallery_id>/photos', type='http', auth='user', methods=['POST'], csrf=False)
    def api_submit_photo(self, gallery_id, **kwargs):
        try:
            user = self._validate_auth()
            gallery = request.env['social_gallery.gallery'].sudo().browse(gallery_id)
            if not gallery.exists():
                return self._error_response('Gallery not found', 'NOT_FOUND', 404)

            body = self._get_json_body()
            attachment_id = body.get('attachment_id') or kwargs.get('attachment_id')
            if not attachment_id:
                return self._error_response('attachment_id required', 'INVALID_INPUT')

            att = request.env['ir.attachment'].sudo().browse(int(attachment_id))
            if not att.exists() or att.create_uid.id != user.id:
                return self._error_response('Invalid attachment', 'INVALID_INPUT')

            state = 'pending' if gallery.is_shared else 'approved'
            photo = request.env['social_gallery.photo'].sudo().create({
                'gallery_id': gallery_id,
                'name': body.get('name') or att.name,
                'submitted_by_id': user.id,
                'state': state,
            })
            att.write({'res_model': 'social_gallery.photo', 'res_id': photo.id})
            return self._success_response(self._photo_to_dict(photo))

        except AccessError as e:
            return self._error_response(str(e), 'AUTH_ERROR', 401)
        except Exception:
            _logger.exception('Error submitting photo')
            return self._error_response('Internal error', 'SUBMIT_ERROR')

    def _gallery_to_dict(self, gallery):
        return {
            'id': gallery.id,
            'name': gallery.name,
            'description': gallery.description,
            'is_shared': gallery.is_shared,
            'visibility': gallery.visibility,
            'photo_count': gallery.approved_photo_count,
            'owner_id': gallery.owner_id.id if gallery.owner_id else None,
        }

    def _photo_to_dict(self, photo):
        return {
            'id': photo.id,
            'name': photo.name,
            'gallery_id': photo.gallery_id.id,
            'state': photo.state,
            'submitted_by_id': photo.submitted_by_id.id if photo.submitted_by_id else None,
            'url': f'/web/image/social_gallery.photo/{photo.id}/image_1920',
            'thumbnail_url': f'/web/image/social_gallery.photo/{photo.id}/image_512',
        }
