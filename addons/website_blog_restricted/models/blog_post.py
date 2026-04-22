from odoo import fields, models


class BlogPost(models.Model):
    _inherit = 'blog.post'

    author_login = fields.Char(compute='_compute_author_login', string="Auteur (login)")

    def _compute_author_login(self):
        for post in self:
            users = post.author_id.sudo().user_ids.filtered(lambda u: u.active)
            post.author_login = users[:1].login if users else post.author_name
