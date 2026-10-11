from odoo import api, fields, models


class HealthResource(models.Model):
    """Ressource locale (clinique, organisme communautaire, ligne d'info).

    Délégation vers res.partner : le contact (nom, adresse, téléphone, site)
    vit dans le partner, la taxonomie santé ici. Les pages publiques ne
    listent que les partners liés à une ressource active — jamais une
    requête ouverte sur res.partner.
    """

    _name = "health.resource"
    _description = "Ressource locale (réduction des risques)"
    _inherits = {"res.partner": "partner_id"}
    _order = "sequence, id"

    # string ≠ « Contact » : res.partner.child_ids porte déjà ce libellé et
    # le doublon déclenche un warning « same label » au chargement.
    partner_id = fields.Many2one(
        "res.partner", string="Fiche contact", required=True,
        ondelete="cascade", index=True)
    resource_type = fields.Selection(
        [
            ("depistage", "Dépistage"),
            ("prep", "PrEP / PEP"),
            ("vaccination", "Vaccination"),
            ("communautaire", "Soutien communautaire"),
            ("urgence", "Urgence / info-santé"),
            ("autre", "Autre"),
        ],
        required=True,
        default="depistage",
        string="Type de ressource",
    )
    region = fields.Char(
        string="Région", translate=True,
        help="Région desservie (ex. Montréal, Québec, province).")
    rdr_notes = fields.Text(
        string="Notes RdR", translate=True,
        help="Infos pratiques : sans rendez-vous, gratuit, "
             "friendly communautés kink/LGBTQ+…")
    sequence = fields.Integer(default=10)
    # Champ propre : archiver une ressource n'archive pas le partner.
    active = fields.Boolean(default=True)

    # Les modérateurs sont en lecture seule sur res.partner (les partners des
    # membres portent leurs vrais noms — on ne leur ouvre pas l'écriture
    # globale). La branche partner de la délégation est donc portée par sudo,
    # une fois l'accès à health.resource vérifié.

    @api.model_create_multi
    def create(self, vals_list):
        self.check_access("create")
        for vals in vals_list:
            vals.setdefault("is_company", True)
        records = super(HealthResource, self.sudo()).create(vals_list)
        return records.with_env(self.env)

    def write(self, vals):
        self.check_access("write")
        return super(HealthResource, self.sudo()).write(vals)
