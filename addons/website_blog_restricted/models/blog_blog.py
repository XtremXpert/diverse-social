from odoo import fields, models


class BlogBlog(models.Model):
    _name = 'blog.blog'
    _inherit = ['blog.blog', 'club.visibility.mixin']

    # Les blogs sont publics par défaut (différent du défaut 'members' du mixin)
    visibility = fields.Selection(default='public')

    # Propriétaire du blog — nécessaire pour le niveau 'connections'
    owner_partner_id = fields.Many2one(
        'res.partner', string="Auteur / Propriétaire",
        help="Utilisé pour les règles de visibilité par connexion. "
             "Laisser vide si le blog n'a pas de propriétaire spécifique.",
    )

    def _visibility_owner_partner(self):
        self.ensure_one()
        return self.owner_partner_id

    def is_accessible_by(self, user):
        """Rétrocompatibilité : accepte un res.users ou un res.partner."""
        self.ensure_one()
        partner = user.partner_id if hasattr(user, 'partner_id') else user
        return self._is_accessible_by(partner)
