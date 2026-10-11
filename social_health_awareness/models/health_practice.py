from odoo import fields, models


class HealthPractice(models.Model):
    _name = "health.practice"
    _description = "Pratique (réduction des risques)"
    _order = "sequence, name"

    name = fields.Char(required=True, translate=True)
    category = fields.Selection(
        [
            ("oral", "Oral"),
            ("penetration", "Pénétration"),
            ("manuel", "Manuel / fisting"),
            ("jouets", "Jouets"),
            ("contact", "Contact peau à peau"),
            ("fluides", "Échange de fluides"),
            ("autre", "Autre"),
        ],
        default="autre",
        string="Catégorie",
    )
    description = fields.Text(translate=True)
    risk_ids = fields.One2many("health.risk", "practice_id", string="Risques")
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
