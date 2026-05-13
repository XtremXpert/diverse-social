import base64

from werkzeug.exceptions import Forbidden, NotFound

from odoo.http import request, route
from odoo.addons.portal.controllers.portal import CustomerPortal, pager as portal_pager


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
    def gallery_detail(self, gallery_id, **kw):
        gallery = request.env['social_gallery.gallery'].browse(gallery_id).exists()
        if not gallery:
            raise NotFound()
        photos = gallery.photo_ids.filtered(lambda p: p.state == 'approved')
        return request.render('social_gallery.portal_gallery_detail', {
            'gallery': gallery,
            'photos': photos,
            'page_name': 'gallery',
        })

    @route('/my/gallery', auth='user', website=True)
    def my_gallery(self, page=1, state='all', **kw):
        domain = [('submitted_by_id', '=', request.env.user.id)]
        if state != 'all':
            domain.append(('state', '=', state))
        total = request.env['social_gallery.photo'].search_count(domain)
        pager = portal_pager(
            url='/my/gallery', url_args={'state': state},
            total=total, page=page, step=12,
        )
        photos = request.env['social_gallery.photo'].search(
            domain, order='id desc', limit=12, offset=pager['offset']
        )
        return request.render('social_gallery.portal_my_gallery', {
            'photos': photos,
            'pager': pager,
            'state_filter': state,
            'page_name': 'gallery',
        })

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
