import json
import logging
from urllib.parse import quote

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)

RESOURCE_TYPE_LABELS = {
    "depistage": "Dépistage",
    "prep": "PrEP / PEP",
    "vaccination": "Vaccination",
    "communautaire": "Soutien communautaire",
    "urgence": "Urgence / info-santé",
    "autre": "Autre",
}


class CoinSante(http.Controller):
    """Page publique du Coin Santé (réduction des risques).

    auth='public' : accessible sans connexion (adapté au QR code en événement).
    Le contenu est de l'information éducative publique — lu en sudo car les
    modèles n'ont pas d'accès public (édition réservée aux modérateurs).
    Aucune donnée personnelle n'est lue ni écrite.
    """

    def _bump(self, page):
        """Compteur agrégé anonyme (page × jour) — ne doit jamais casser le rendu."""
        try:
            request.env["health.page.view"].sudo()._bump(page)
        except Exception:
            _logger.exception("Coin Santé : échec d'incrément du compteur %s", page)

    def _resource_groups(self):
        """Ressources locales actives, groupées par type (ordre de la sélection)."""
        resources = request.env["health.resource"].sudo().search([("active", "=", True)])
        groups = []
        by_type = {}
        for res_type, label in RESOURCE_TYPE_LABELS.items():
            group = {"key": res_type, "label": label, "resources": []}
            by_type[res_type] = group
        for r in resources:
            by_type.get(r.resource_type or "autre", by_type["autre"])["resources"].append(r)
        for res_type in RESOURCE_TYPE_LABELS:
            if by_type[res_type]["resources"]:
                groups.append(by_type[res_type])
        return groups

    @http.route(["/sante", "/reduction-des-risques"], type="http", auth="public", website=True, sitemap=True)
    def coin_sante(self, **kw):
        Practice = request.env["health.practice"].sudo()
        Prevention = request.env["health.prevention"].sudo()

        practices = Practice.search([("active", "=", True)])
        guide = []
        for p in practices:
            risks = p.risk_ids.filtered(lambda r: r.infection_id.active)
            prevs = Prevention.search([
                ("active", "=", True),
                ("is_transversal", "=", False),
                ("practice_ids", "in", p.id),
            ])
            guide.append({"practice": p, "risks": risks, "preventions": prevs})

        transversal = Prevention.search([("active", "=", True), ("is_transversal", "=", True)])

        self._bump("sante")
        return request.render("social_health_awareness.coin_sante_page", {
            "guide": guide,
            "transversal": transversal,
            "resource_groups": self._resource_groups(),
            "level_labels": {"faible": "Faible", "modere": "Modéré", "eleve": "Élevé"},
            "level_class": {"faible": "bg-success", "modere": "bg-warning text-dark", "eleve": "bg-danger"},
        })

    @http.route(["/sante/auto-evaluation"], type="http", auth="public", website=True, sitemap=True)
    def coin_sante_autoeval(self, **kw):
        """Auto-évaluation anonyme (Phase 2).

        La matrice complète est embarquée dans la page ; la sélection des
        pratiques et le calcul du résumé se font entièrement dans le
        navigateur. Aucune réponse n'est transmise au serveur ni stockée —
        cocher une case ne déclenche aucune requête.
        """
        Practice = request.env["health.practice"].sudo()
        Infection = request.env["health.infection"].sudo()
        Prevention = request.env["health.prevention"].sudo()

        practices = Practice.search([("active", "=", True)])
        infections = Infection.search([("active", "=", True)])
        preventions = Prevention.search([("active", "=", True)])

        category_labels = dict(
            Practice._fields["category"]._description_selection(request.env)
        )

        payload = {
            "practices": [
                {
                    "id": p.id,
                    "name": p.name,
                    "description": p.description or "",
                }
                for p in practices
            ],
            "infections": {
                str(i.id): {
                    "name": i.name,
                    "window": i.window_period or "",
                    "screening": i.screening or "",
                    "vaccine": i.vaccine_available,
                }
                for i in infections
            },
            "risks": [
                {
                    "p": r.practice_id.id,
                    "i": r.infection_id.id,
                    "level": r.level,
                    "note": r.note or "",
                }
                for p in practices
                for r in p.risk_ids
                if r.infection_id.active
            ],
            "preventions": [
                {
                    "name": v.name,
                    "description": v.description or "",
                    "transversal": v.is_transversal,
                    "practices": v.practice_ids.ids,
                    "infections": v.infection_ids.ids,
                }
                for v in preventions
            ],
        }

        # Regrouper les pratiques par catégorie (ordre de première apparition)
        # pour le formulaire QWeb.
        groups_by_cat = {}
        groups = []
        for p in practices:
            cat = p.category or "autre"
            if cat not in groups_by_cat:
                group = {
                    "key": cat,
                    "label": category_labels.get(cat, "Autre"),
                    "practices": [],
                }
                groups_by_cat[cat] = group
                groups.append(group)
            groups_by_cat[cat]["practices"].append(p)

        self._bump("autoeval")
        return request.render("social_health_awareness.coin_sante_autoeval_page", {
            "practice_groups": groups,
            "payload_json": json.dumps(payload, ensure_ascii=False),
            "resource_groups": self._resource_groups(),
        })

    @http.route(["/sante/affiche"], type="http", auth="public", website=True, sitemap=False)
    def coin_sante_affiche(self, **kw):
        """Affiche imprimable pour le « coin santé » physique en événement.

        QR vers /sante, généré par le service de codes-barres d'Odoo —
        aucune dépendance externe.
        """
        base_url = request.env.website.get_base_url()
        sante_url = base_url + "/sante"
        qr_src = "/report/barcode/?barcode_type=QR&value=%s&width=300&height=300" % quote(sante_url, safe="")
        return request.render("social_health_awareness.coin_sante_affiche_page", {
            "sante_url": sante_url,
            "qr_src": qr_src,
        })
