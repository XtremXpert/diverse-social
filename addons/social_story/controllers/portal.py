from werkzeug.exceptions import Forbidden, NotFound

from odoo.http import request, route
from odoo.addons.portal.controllers.portal import CustomerPortal


class StoryPortal(CustomerPortal):

    def _prepare_home_portal_values(self, counters):
        values = super()._prepare_home_portal_values(counters)
        if 'my_stories_count' in counters:
            values['my_stories_count'] = request.env['social_story.story'].search_count([
                ('author_id', '=', request.env.user.id),
                ('state', '=', 'active'),
            ])
        return values

    @route('/my/stories', auth='user', website=True)
    def my_stories(self, filter='active', **kw):
        domain = [('author_id', '=', request.env.user.id)]
        if filter == 'active':
            domain.append(('state', '=', 'active'))
        elif filter == 'expired':
            domain.append(('state', '=', 'expired'))
        stories = request.env['social_story.story'].search(domain, order='id desc')
        return request.render('social_story.portal_my_stories', {
            'stories': stories,
            'filter': filter,
            'page_name': 'stories',
        })

    @route('/my/stories/<int:story_id>/archive', auth='user', methods=['POST'], website=True, csrf=True)
    def story_archive(self, story_id, **kw):
        story = request.env['social_story.story'].browse(story_id).exists()
        if not story or story.author_id != request.env.user:
            raise Forbidden()
        story.action_archive()
        return request.redirect('/my/stories')
