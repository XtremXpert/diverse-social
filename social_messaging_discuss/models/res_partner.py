from odoo import models
from odoo.addons.mail.tools.discuss import Store


class ResPartner(models.Model):
    """Pseudonymise les noms de partenaires dans le Store Discuss.

    Tout ce que le client Discuss (OWL) affiche — nom du correspondant dans
    l'en-tête, liste des canaux, auteurs des messages, titre d'onglet — vient
    de la sérialisation Store de res.partner. Pour un membre portail, on ne
    doit JAMAIS exposer le vrai nom d'un autre membre : on substitue le
    pseudonyme (stealth_name) via le helper canonique du profil.

    Les utilisateurs internes (modération / backoffice) continuent de voir
    les vrais noms.
    """
    _inherit = 'res.partner'

    def _field_store_repr(self, field_name):
        if field_name == "name" and not self.env.user._is_internal():
            return [Store.Attr("name", lambda p: p._social_display_name())]
        return super()._field_store_repr(field_name)

    def _social_display_name(self):
        self.ensure_one()
        user = self.sudo().user_ids[:1]
        if not user:
            # Partenaire sans utilisateur (OdooBot, compagnie…) : nom inchangé.
            return self.name
        return self.env['club_social_profile.profile']._display_name_for_user(user)
