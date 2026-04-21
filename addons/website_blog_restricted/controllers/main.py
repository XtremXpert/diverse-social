from odoo.addons.website_blog.controllers.main import WebsiteBlog
from odoo.http import request


class WebsiteBlogRestricted(WebsiteBlog):

    def _is_blog_accessible(self, blog):
        return blog.is_accessible_by(request.env.user)

    def _prepare_blog_values(self, blogs, **kwargs):
        user = request.env.user
        accessible = blogs.filtered(lambda b: b.is_accessible_by(user))
        return super()._prepare_blog_values(blogs=accessible, **kwargs)

    def blog(self, blog=None, **kwargs):
        if blog and not self._is_blog_accessible(blog):
            redirect_url = request.httprequest.full_path
            return request.redirect('/web/login?redirect=%s' % redirect_url)
        return super().blog(blog=blog, **kwargs)

    def blog_post(self, blog, blog_post, **post):
        if not self._is_blog_accessible(blog):
            redirect_url = request.httprequest.full_path
            return request.redirect('/web/login?redirect=%s' % redirect_url)
        return super().blog_post(blog, blog_post, **post)
