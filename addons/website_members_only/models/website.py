from odoo import fields, models


class Website(models.Model):
    _inherit = 'website'

    event_login_required = fields.Boolean(
        string="Événements réservés aux membres",
        default=True,
        help="Si activé, les visiteurs non connectés sont redirigés vers la page de connexion "
             "lorsqu'ils tentent d'accéder à la liste des événements ou à un événement.",
    )
