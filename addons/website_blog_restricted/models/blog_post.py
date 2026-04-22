from odoo import fields, models


class BlogPost(models.Model):
    _inherit = 'blog.post'

    author_login = fields.Char(compute='_compute_author_login', string="Auteur (login)")

    def _compute_author_login(self):
        for post in self:
            users = post.author_id.sudo().user_ids
            portal_users = users.filtered(lambda u: u.share and u.active)
            internal_users = users.filtered(lambda u: not u.share and u.active)
            if portal_users and not internal_users:
                post.author_login = portal_users[:1].login
            else:
                post.author_login = post.author_name
