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
            'error': kw.get('error'),
        })

    @route('/groups/create', auth='user', methods=['POST'], website=True, csrf=True)
    def group_create(self, name='', description='', privacy='private', join_type='approval', **kw):
        name = (name or '').strip()
        if not name:
            return request.redirect('/groups?error=name_required')
        if privacy not in ('public', 'private', 'secret'):
            privacy = 'private'
        if join_type not in ('open', 'approval', 'invite'):
            join_type = 'approval'
        try:
            group = request.env['social_group.group'].with_user(request.env.user).create({
                'name': name,
                'description': (description or '').strip() or False,
                'privacy': privacy,
                'join_type': join_type,
                'admin_ids': [(4, request.env.user.id)],
                'member_ids': [(4, request.env.user.id)],
            })
        except Exception:
            return request.redirect('/groups?error=create_failed')
        return request.redirect(f'/groups/{group.id}?created=1')

    @route('/groups/<int:group_id>', auth='user', website=True)
    def group_detail(self, group_id, **kw):
        group = request.env['social_group.group'].sudo().browse(group_id).exists()
        if not group or group.privacy == 'secret' and not group.is_member(request.env.user):
            raise NotFound()
        user = request.env.user
        is_member = group.is_member(user)
        is_mod = group.is_moderator(user)
        pending_request = request.env['social_group.join_request'].search([
            ('group_id', '=', group.id),
            ('user_id', '=', user.id),
            ('state', '=', 'pending'),
        ], limit=1)
        pending_requests = request.env['social_group.join_request'].sudo().search([
            ('group_id', '=', group.id),
            ('state', '=', 'pending'),
        ]) if is_mod else request.env['social_group.join_request']
        posts = request.env['social_base.post'].sudo().search([
            ('group_id', '=', group.id),
            ('state', '=', 'published'),
        ], limit=20, order='id desc') if is_member else request.env['social_base.post']
        return request.render('social_group.portal_group_detail', {
            'group': group,
            'is_member': is_member,
            'is_mod': is_mod,
            'pending_request': pending_request,
            'pending_requests': pending_requests,
            'posts': posts,
            'page_name': 'groups',
            'error': kw.get('error'),
        })

    @route('/groups/<int:group_id>/edit', auth='user', methods=['POST'], website=True, csrf=True)
    def group_edit(self, group_id, name='', description='', privacy='private', join_type='approval', **kw):
        group = request.env['social_group.group'].sudo().browse(group_id).exists()
        if not group:
            raise NotFound()
        user = request.env.user
        if not group.is_admin(user) and not user.has_group('social_base.group_social_moderator'):
            raise Forbidden()
        name = (name or '').strip()
        if not name:
            return request.redirect(f'/groups/{group_id}?error=name_required')
        if privacy not in ('public', 'private', 'secret'):
            privacy = group.privacy
        if join_type not in ('open', 'approval', 'invite'):
            join_type = group.join_type
        group.sudo().write({
            'name': name,
            'description': (description or '').strip() or False,
            'privacy': privacy,
            'join_type': join_type,
        })
        return request.redirect(f'/groups/{group_id}?edited=1')

    @route('/groups/<int:group_id>/requests/<int:req_id>/approve', auth='user',
           methods=['POST'], website=True, csrf=True)
    def group_request_approve(self, group_id, req_id, **kw):
        group = request.env['social_group.group'].sudo().browse(group_id).exists()
        if not group:
            raise NotFound()
        if not group.is_moderator(request.env.user):
            raise Forbidden()
        join_req = request.env(su=True)['social_group.join_request'].browse(req_id).exists()
        if not join_req or join_req.group_id.id != group_id or join_req.state != 'pending':
            raise NotFound()
        join_req.action_approve()
        return request.redirect(f'/groups/{group_id}?approved=1')

    @route('/groups/<int:group_id>/requests/<int:req_id>/reject', auth='user',
           methods=['POST'], website=True, csrf=True)
    def group_request_reject(self, group_id, req_id, **kw):
        group = request.env['social_group.group'].sudo().browse(group_id).exists()
        if not group:
            raise NotFound()
        if not group.is_moderator(request.env.user):
            raise Forbidden()
        join_req = request.env(su=True)['social_group.join_request'].browse(req_id).exists()
        if not join_req or join_req.group_id.id != group_id or join_req.state != 'pending':
            raise NotFound()
        join_req.action_reject()
        return request.redirect(f'/groups/{group_id}?rejected=1')

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
