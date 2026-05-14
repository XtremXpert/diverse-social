import base64

from werkzeug.exceptions import Forbidden, NotFound

from odoo.http import request, route
from odoo.addons.portal.controllers.portal import CustomerPortal, pager as portal_pager

_GALLERY_STEP = 24


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
        galleries = request.env['social_gallery.gallery'].search(
            [('visibility', 'in', ['public', 'members'])], order='sequence, id'
        )
        return request.render('social_gallery.portal_gallery_list', {
            'galleries': galleries,
            'page_name': 'gallery',
        })

    @route('/gallery/<int:gallery_id>', auth='user', website=True)
    def gallery_detail(self, gallery_id, page=1, **kw):
        gallery = request.env['social_gallery.gallery'].browse(gallery_id).exists()
        if not gallery:
            raise NotFound()

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
        if visibility not in ('public', 'members', 'private'):
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
    def gallery_submit_photo(self, gallery_id, name='', image=None, **kw):
        gallery = request.env['social_gallery.gallery'].browse(gallery_id).exists()
        if not gallery or not gallery.is_shared:
            raise Forbidden()
        if not image or not getattr(image, 'filename', None):
            return request.redirect('/gallery/%d?error=image_required' % gallery_id)
        image_data = base64.b64encode(image.read()).decode('ascii')
        request.env['social_gallery.photo'].create({
            'gallery_id': gallery.id,
            'name': (name or '').strip() or image.filename,
            'image_1920': image_data,
            'submitted_by_id': request.env.user.id,
            'state': 'pending',
        })
        return request.redirect('/gallery/%d?success=1' % gallery_id)
