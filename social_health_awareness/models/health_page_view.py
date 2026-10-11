from odoo import api, fields, models


class HealthPageView(models.Model):
    """Compteur agrégé de consultations — AUCUNE donnée individuelle.

    Un enregistrement = (page, jour, total). Pas d'IP, pas de session,
    pas d'user_id : l'incrément se fait en SQL brut sans passer par
    l'ORM, donc create_uid/create_date restent NULL même pour un
    visiteur connecté. Les sélections de l'auto-évaluation ne sont
    jamais comptées (elles ne quittent pas le navigateur).
    """

    _name = "health.page.view"
    _description = "Consultations Coin Santé (agrégat anonyme)"
    _order = "date desc, page"

    page = fields.Char(required=True, index=True)
    date = fields.Date(required=True)
    count = fields.Integer(default=0, string="Consultations")

    _page_date_uniq = models.Constraint(
        "UNIQUE (page, date)",
        "Un seul compteur par page et par jour.")

    @api.model
    def _bump(self, page):
        """Incrémente le compteur du jour pour `page` (upsert atomique)."""
        # Savepoint : un échec SQL ne doit pas avorter la transaction de la
        # requête HTTP appelante.
        with self.env.cr.savepoint():
            self.env.cr.execute(
                """
                INSERT INTO health_page_view (page, date, count)
                VALUES (%s, CURRENT_DATE, 1)
                ON CONFLICT (page, date)
                DO UPDATE SET count = health_page_view.count + 1
                """,
                [page],
            )
