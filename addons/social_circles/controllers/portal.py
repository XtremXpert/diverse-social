from werkzeug.exceptions import Forbidden, NotFound

from odoo.http import request, route
from odoo.addons.portal.controllers.portal import CustomerPortal


class CirclesPortal(CustomerPortal):

    def _prepare_home_portal_values(self, counters):
        values = super()._prepare_home_portal_values(counters)
        if 'my_circles_count' in counters:
            profile = request.env['club_social_profile.profile'].sudo().search([
                ('user_id', '=', request.env.user.id),
            ], limit=1)
            values['my_circles_count'] = request.env['social_circles.circle'].search_count([
                ('profile_id', '=', profile.id),
            ]) if profile else 0
        return values

    @route('/my/circles', auth='user', website=True)
    def my_circles(self, **kw):
        profile = request.env['club_social_profile.profile'].get_or_create_for_user(request.env.user)
        circles = request.env['social_circles.circle'].search([
            ('profile_id', '=', profile.id),
        ], order='sequence, id')
        return request.render('social_circles.portal_my_circles', {
            'circles': circles,
            'profile': profile,
            'page_name': 'circles',
        })

    @route('/my/circles/create', auth='user', methods=['POST'], website=True, csrf=True)
    def circle_create(self, name='', description='', **kw):
        name = name.strip()
        if not name:
            return request.redirect('/my/circles?error=name_required')
        profile = request.env['club_social_profile.profile'].get_or_create_for_user(request.env.user)
        request.env['social_circles.circle'].create({
            'profile_id': profile.id,
            'name': name,
            'description': description.strip() or False,
        })
        return request.redirect('/my/circles')

    @route('/my/circles/<int:circle_id>/delete', auth='user', methods=['POST'], website=True, csrf=True)
    def circle_delete(self, circle_id, **kw):
        circle = request.env['social_circles.circle'].browse(circle_id).exists()
        if not circle or circle.profile_id.user_id != request.env.user:
            raise Forbidden()
        circle.sudo().unlink()
        return request.redirect('/my/circles')

    @route('/my/circles/<int:circle_id>/remove_member', auth='user', methods=['POST'], website=True, csrf=True)
    def circle_remove_member(self, circle_id, user_id=None, **kw):
        circle = request.env['social_circles.circle'].browse(circle_id).exists()
        if not circle or circle.profile_id.user_id != request.env.user:
            raise Forbidden()
        if user_id:
            member = request.env['res.users'].sudo().browse(int(user_id)).exists()
            if member:
                circle.remove_member(member)
        return request.redirect('/my/circles')
