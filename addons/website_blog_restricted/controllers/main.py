from odoo.addons.website_blog.controllers.main import WebsiteBlog
from odoo.http import request


class WebsiteBlogRestricted(WebsiteBlog):

    def _is_blog_accessible(self, blog):
        return blog.is_accessible_by(request.env.user)

    def _prepare_blog_values(self, blogs, **kwargs):
        user = request.env.user
        if self._is_internal_user():
            accessible = blogs
        else:
            accessible = blogs.filtered(lambda b: b.is_accessible_by(user))
        values = super()._prepare_blog_values(blogs=accessible, **kwargs)
        # Filter posts: _search_with_fuzzy n'est pas conscient des restrictions
        # de visibilité, donc des articles de blogs inaccessibles peuvent apparaître.
        if isinstance(values, dict) and accessible:
            accessible_ids = set(accessible.ids)
            values['posts'] = values['posts'].filtered(
                lambda p: p.blog_id.id in accessible_ids
            )
        return values

    def _is_internal_user(self):
        """Retourne True si l'utilisateur courant est un utilisateur interne (non portail, non public)."""
        user = request.env.user
        return user.active and not user.share

    def blog(self, blog=None, **kwargs):
        if blog and not self._is_internal_user() and not self._is_blog_accessible(blog):
            redirect_url = request.httprequest.full_path
            return request.redirect('/web/login?redirect=%s' % redirect_url, code=302)
        return super().blog(blog=blog, **kwargs)

    def blog_post(self, blog, blog_post, **post):
        if not self._is_internal_user() and not self._is_blog_accessible(blog):
            redirect_url = request.httprequest.full_path
            return request.redirect('/web/login?redirect=%s' % redirect_url, code=302)
        return super().blog_post(blog, blog_post, **post)
