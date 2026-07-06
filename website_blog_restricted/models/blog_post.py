from odoo import fields, models


class BlogPost(models.Model):
    _inherit = 'blog.post'

    author_login = fields.Char(compute='_compute_author_login', string="Auteur (pseudonyme)")

    def _compute_author_login(self):
        Profile = self.env['club_social_profile.profile']
        for post in self:
            users = post.author_id.sudo().user_ids.filtered(lambda u: u.active)
            # Pseudonyme (stealth_name) — le login peut être un courriel,
            # on ne l'expose jamais aux autres membres.
            post.author_login = (
                Profile._display_name_for_user(users[:1]) if users else post.author_name
            )
