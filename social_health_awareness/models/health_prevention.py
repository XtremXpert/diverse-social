from odoo import fields, models


class HealthPrevention(models.Model):
    _name = "health.prevention"
    _description = "Mesure de réduction des risques"
    _order = "sequence, name"

    name = fields.Char(required=True, translate=True)
    description = fields.Text(translate=True)
    prevention_type = fields.Selection(
        [
            ("barriere", "Barrière (condom, gant, digue)"),
            ("vaccin", "Vaccination"),
            ("prep", "PrEP / PEP"),
            ("depistage", "Dépistage"),
            ("hygiene", "Hygiène / matériel"),
            ("communication", "Communication"),
            ("autre", "Autre"),
        ],
        default="autre",
        string="Type",
    )
    # Mesure transversale : s'applique largement (PrEP, vaccination, U=U,
    # dépistage régulier) plutôt qu'à une pratique précise.
    is_transversal = fields.Boolean(string="Mesure transversale")
    practice_ids = fields.Many2many("health.practice", string="Pratiques concernées")
    infection_ids = fields.Many2many("health.infection", string="Infections concernées")
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
