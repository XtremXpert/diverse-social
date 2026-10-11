{
    "name": "Coin Santé — réduction des risques",
    "version": "20.0.3.1.0",
    "category": "Website/Health",
    "summary": "Guide anonyme de réduction des risques (pratiques → risques → prévention), "
               "sans stigmatisation ni donnée de santé personnelle",
    "description": """
Approche de sensibilisation et de réduction des risques (RdR), en remplacement
d'un « passeport santé » stigmatisant.

Principe : on parle de PRATIQUES et de RISQUES, jamais de PERSONNES et de
STATUTS. Aucune donnée de santé individuelle n'est collectée ni stockée.

Phase 1 :

- Matrice éditable par les modérateurs : pratiques, infections, niveaux de
  risque et mesures de prévention.
- Page publique /sante (sans connexion, adaptée au QR code en événement) qui
  affiche le guide, avec un disclaimer clair.

Phase 2 :

- Auto-évaluation anonyme /sante/auto-evaluation : la personne coche les
  pratiques envisagées et obtient un résumé (infections pertinentes, niveau
  de risque, mesures de réduction, dépistage suggéré). Calcul 100 % côté
  navigateur : aucune réponse transmise ni stockée.

Phase 3 :

- Ressources locales (health.resource, délégation res.partner) : dépistage,
  PrEP/PEP, vaccination, soutien communautaire — affichées sur /sante et
  dans l'auto-évaluation, éditables par les modérateurs.
- Affiche QR imprimable /sante/affiche pour le coin santé physique en
  événement.
- Entrée « Coin Santé » dans le portail membre (/my) et liens depuis la page
  Sécurité et les négociations.
- Compteurs de consultations agrégés anonymes (page et jour, sans IP, sans
  session, sans user) — les sélections de l'auto-évaluation ne quittent
  jamais le navigateur.

⚠️ Le contenu fourni est un PLACEHOLDER à faire valider par un professionnel de
la santé avant toute mise en ligne réelle.
    """,
    "author": "Bemade",
    "license": "LGPL-3",
    "depends": ["website", "social_base", "social_safety", "social_negotiation"],
    "data": [
        'security/ir.access.csv',
        'views/health_backend_views.xml',
        'views/health_website_templates.xml',
        'data/health_data.xml',
        'data/health_resources.xml',
        'data/portal_entry_data.xml',
    ],
    "assets": {
        "web.assets_frontend": [
            "social_health_awareness/static/src/js/coin_sante_autoeval.js",
        ],
    },
    "installable": True,
    "application": True,
}
