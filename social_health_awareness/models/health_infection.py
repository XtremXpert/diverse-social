from odoo import fields, models


class HealthInfection(models.Model):
    _name = "health.infection"
    _description = "Infection (réduction des risques)"
    _order = "sequence, name"

    name = fields.Char(required=True, translate=True)
    description = fields.Text(translate=True)
    window_period = fields.Char(
        string="Délai fenêtre", translate=True,
        help="Délai avant qu'un dépistage soit fiable.")
    screening = fields.Char(
        string="Dépistage", translate=True,
        help="Comment se faire dépister (prélèvement, site).")
    vaccine_available = fields.Boolean(string="Vaccin disponible")
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
