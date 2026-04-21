from odoo import fields, models


class BlogBlog(models.Model):
    _inherit = 'blog.blog'

    restricted_user_ids = fields.Many2many(
        'res.users',
        string="Visible uniquement par",
        help="Si rempli, seuls ces utilisateurs connectés peuvent voir ce blog et ses articles. "
             "Laissez vide pour un accès public.",
    )

    def is_accessible_by(self, user):
        """Retourne True si l'utilisateur peut accéder à ce blog."""
        self.ensure_one()
        if not self.restricted_user_ids:
            return True
        return user in self.restricted_user_ids
