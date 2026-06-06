import base64

from werkzeug.exceptions import Forbidden, NotFound

from odoo.http import request, route
from odoo.addons.portal.controllers.portal import CustomerPortal, pager as portal_pager

_GALLERY_STEP = 24
_MAX_MEDIA_BYTES = 25 * 1024 * 1024  # 25 Mo
_VIDEO_MIMETYPES = ('video/mp4', 'video/webm', 'video/ogg', 'video/quicktime')
_VIDEO_EXTS = ('.mp4', '.webm', '.ogg', '.ogv', '.mov')


class GalleryPortal(CustomerPortal):

    def _prepare_home_portal_values(self, counters):
        values = super()._prepare_home_portal_values(counters)
        if 'gallery_pending_count' in counters:
            values['gallery_pending_count'] = request.env['social_gallery.photo'].search_count([
                ('submitted_by_id', '=', request.env.user.id),
                ('state', '=', 'pending'),
            ])
        return values

    @route('/gallery', auth='user', website=True, sitemap=True)
    def gallery_list(self, **kw):
        user = request.env.user
        galleries = request.env['social_gallery.gallery'].search([], order='sequence, id')
        galleries = galleries.filtered(lambda g: g.is_accessible_by(user))
        return request.render('social_gallery.portal_gallery_list', {
            'galleries': galleries,
            'page_name': 'gallery',
        })

    @route('/gallery/<int:gallery_id>', auth='user', website=True)
    def gallery_detail(self, gallery_id, page=1, **kw):
        gallery = request.env['social_gallery.gallery'].browse(gallery_id).exists()
        if not gallery:
            raise NotFound()
        if not gallery.is_accessible_by(request.env.user):
            raise Forbidden()

        approved = gallery.photo_ids.filtered(lambda p: p.state == 'approved').sorted('sequence')
        total = len(approved)
        pager = portal_pager(
            url=f'/gallery/{gallery_id}',
            total=total, page=int(page), step=_GALLERY_STEP,
        )
        photos = approved[pager['offset']:pager['offset'] + _GALLERY_STEP]

        owner_profile = None
        if gallery.owner_id and 'club_social_profile.profile' in request.env:
            owner_profile = request.env['club_social_profile.profile'].sudo().search(
                [('user_id', '=', gallery.owner_id.id)], limit=1
            )

        return request.render('social_gallery.portal_gallery_detail', {
            'gallery': gallery,
            'photos': photos,
            'pager': pager,
            'owner_profile': owner_profile,
            'page_name': 'gallery',
        })

    @route('/my/gallery', auth='user', website=True)
    def my_gallery(self, page=1, state='all', **kw):
        user = request.env.user
        domain = [('submitted_by_id', '=', user.id)]
        if state != 'all':
            domain.append(('state', '=', state))
        total = request.env['social_gallery.photo'].search_count(domain)
        pager = portal_pager(
            url='/my/gallery', url_args={'state': state},
            total=total, page=int(page), step=12,
        )
        photos = request.env['social_gallery.photo'].search(
            domain, order='id desc', limit=12, offset=pager['offset']
        )
        my_galleries = request.env['social_gallery.gallery'].search(
            [('owner_id', '=', user.id)], order='sequence, id'
        )
        return request.render('social_gallery.portal_my_gallery', {
            'photos': photos,
            'pager': pager,
            'state_filter': state,
            'my_galleries': my_galleries,
            'page_name': 'gallery',
        })

    @route('/my/gallery/create', auth='user', methods=['POST'], website=True, csrf=True)
    def my_gallery_create(self, name='', description='', visibility='members', **kw):
        name = (name or '').strip()
        if not name:
            return request.redirect('/my/gallery?error=name_required')
        if visibility not in ('public', 'members', 'connections'):
            visibility = 'members'
        request.env['social_gallery.gallery'].sudo().create({
            'name': name,
            'description': (description or '').strip() or False,
            'owner_id': request.env.user.id,
            'visibility': visibility,
            'is_shared': False,
        })
        return request.redirect('/my/gallery?created=1')

    @route('/my/gallery/photo/<int:photo_id>/delete', auth='user', methods=['POST'], website=True, csrf=True)
    def my_gallery_photo_delete(self, photo_id, **kw):
        photo = request.env['social_gallery.photo'].sudo().browse(photo_id)
        if not photo.exists():
            return request.redirect('/my/gallery')
        if photo.submitted_by_id.id != request.env.user.id:
            raise Forbidden()
        if photo.state == 'approved':
            raise Forbidden()
        gallery_id = photo.gallery_id.id
        photo.unlink()
        if gallery_id:
            return request.redirect(f'/gallery/{gallery_id}?deleted=1')
        return request.redirect('/my/gallery?deleted=1')

    @route('/gallery/<int:gallery_id>/submit', auth='user', methods=['POST'], website=True, csrf=True)
    def gallery_submit_photo(self, gallery_id, name='', media=None, image=None, **kw):
        gallery = request.env['social_gallery.gallery'].browse(gallery_id).exists()
        if not gallery:
            raise NotFound()
        user = request.env.user
        is_owner = gallery.owner_id.id == user.id
        # Le propriétaire ajoute à sa propre galerie ; les autres ne peuvent
        # soumettre que sur une galerie participative (modérée).
        if not (is_owner or gallery.is_shared):
            raise Forbidden()

        # `image` accepté pour rétro-compat ; `media` est le champ courant.
        upload = media or image
        if not upload or not getattr(upload, 'filename', None):
            return request.redirect('/gallery/%d?error=media_required' % gallery_id)

        filename = upload.filename
        content_type = (getattr(upload, 'content_type', '') or '').lower()
        ext = filename.lower().rsplit('.', 1)[-1] if '.' in filename else ''
        is_video = content_type in _VIDEO_MIMETYPES or ('.' + ext) in _VIDEO_EXTS
        is_image = content_type.startswith('image/') or (not is_video and ('.' + ext) in (
            '.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.heic', '.heif'))
        if not (is_video or is_image):
            return request.redirect('/gallery/%d?error=bad_type' % gallery_id)

        data = upload.read()
        if len(data) > _MAX_MEDIA_BYTES:
            return request.redirect('/gallery/%d?error=too_large' % gallery_id)
        encoded = base64.b64encode(data).decode('ascii')

        vals = {
            'gallery_id': gallery.id,
            'name': (name or '').strip() or filename,
            'submitted_by_id': user.id,
            # Sa propre galerie → publié direct ; soumission tierce → modération.
            'state': 'approved' if is_owner else 'pending',
        }
        if is_video:
            vals.update({
                'media_type': 'video',
                'video_file': encoded,
                'video_filename': filename,
            })
        else:
            vals.update({
                'media_type': 'image',
                'image_1920': encoded,
            })
        request.env['social_gallery.photo'].create(vals)
        return request.redirect('/gallery/%d?success=1' % gallery_id)
