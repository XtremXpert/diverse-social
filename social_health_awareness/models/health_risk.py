from odoo import api, fields, models


class HealthRisk(models.Model):
    _name = "health.risk"
    _description = "Risque : pratique × infection"
    _order = "practice_id, infection_id"

    name = fields.Char(compute="_compute_name", store=True)
    practice_id = fields.Many2one("health.practice", required=True, ondelete="cascade", index=True)
    infection_id = fields.Many2one("health.infection", required=True, ondelete="cascade", index=True)
    level = fields.Selection(
        [
            ("faible", "Faible"),
            ("modere", "Modéré"),
            ("eleve", "Élevé"),
        ],
        required=True,
        default="modere",
        string="Niveau de risque",
    )
    note = fields.Text(translate=True)

    _practice_infection_uniq = models.Constraint(
        "UNIQUE (practice_id, infection_id)",
        "Ce couple pratique / infection existe déjà.")

    @api.depends("practice_id.name", "infection_id.name")
    def _compute_name(self):
        for r in self:
            r.name = "%s — %s" % (r.practice_id.name or "", r.infection_id.name or "")
