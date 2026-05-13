from werkzeug.exceptions import Forbidden, NotFound

from odoo.http import request, route
from odoo.addons.portal.controllers.portal import CustomerPortal, pager as portal_pager


class GroupPortal(CustomerPortal):

    def _prepare_home_portal_values(self, counters):
        values = super()._prepare_home_portal_values(counters)
        if 'my_groups_count' in counters:
            values['my_groups_count'] = request.env['social_group.group'].search_count([
                ('member_ids', 'in', request.env.user.id),
            ])
        return values

    @route('/groups', auth='user', website=True, sitemap=True)
    def group_list(self, page=1, **kw):
        # sudo: ir.rule hides secret groups; show public+private for browsing
        Group = request.env['social_group.group'].sudo()
        domain = [('privacy', 'in', ['public', 'private'])]
        total = Group.search_count(domain)
        pager = portal_pager(
            url='/groups', total=total, page=page, step=12,
        )
        groups = Group.search(domain, order='name', limit=12, offset=pager['offset'])
        my_ids = request.env['social_group.group'].search([
            ('member_ids', 'in', request.env.user.id)
        ]).ids
        return request.render('social_group.portal_group_list', {
            'groups': groups,
            'pager': pager,
            'my_group_ids': my_ids,
            'page_name': 'groups',
        })

    @route('/groups/<int:group_id>', auth='user', website=True)
    def group_detail(self, group_id, **kw):
        group = request.env['social_group.group'].sudo().browse(group_id).exists()
        if not group or group.privacy == 'secret' and not group.is_member(request.env.user):
            raise NotFound()
        is_member = group.is_member(request.env.user)
        pending_request = request.env['social_group.join_request'].search([
            ('group_id', '=', group.id),
            ('user_id', '=', request.env.user.id),
            ('state', '=', 'pending'),
        ], limit=1)
        posts = request.env['social_base.post'].sudo().search([
            ('group_id', '=', group.id),
            ('state', '=', 'published'),
        ], limit=20, order='id desc') if is_member else request.env['social_base.post']
        return request.render('social_group.portal_group_detail', {
            'group': group,
            'is_member': is_member,
            'pending_request': pending_request,
            'posts': posts,
            'page_name': 'groups',
        })

    @route('/groups/<int:group_id>/join', auth='user', methods=['POST'], website=True, csrf=True)
    def group_join(self, group_id, **kw):
        group = request.env['social_group.group'].sudo().browse(group_id).exists()
        if not group or group.privacy == 'secret':
            raise Forbidden()
        try:
            group.with_user(request.env.user).action_join()
        except Exception:
            pass
        return request.redirect('/groups/%d' % group_id)

    @route('/groups/<int:group_id>/leave', auth='user', methods=['POST'], website=True, csrf=True)
    def group_leave(self, group_id, **kw):
        group = request.env['social_group.group'].sudo().browse(group_id).exists()
        if not group:
            raise NotFound()
        try:
            group.with_user(request.env.user).action_leave()
        except Exception:
            pass
        return request.redirect('/groups/%d' % group_id)

    @route('/my/groups', auth='user', website=True)
    def my_groups(self, **kw):
        groups = request.env['social_group.group'].search([
            ('member_ids', 'in', request.env.user.id),
        ], order='name')
        return request.render('social_group.portal_my_groups', {
            'groups': groups,
            'page_name': 'groups',
        })
