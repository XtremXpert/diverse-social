from odoo import models


class Website(models.Model):
    _inherit = 'website'

    def _product_domain(self):
        """Exclure les produits de billets d'événements de la boutique.
        L'achat se fait uniquement via la page de l'événement.
        """
        return super()._product_domain() + [('service_tracking', '!=', 'event')]
