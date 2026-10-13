{
    "name": "Événements — création portail",
    "version": "20.0.2.0.0",
    "category": "Marketing/Events",
    "summary": "Laisse les membres du groupe « Organisateur portail » créer et gérer "
               "leurs propres événements depuis le portail/site, sans accès backend",
    "description": """
Ajoute un espace portail « Mes événements » réservé aux membres du groupe
« Organisateur portail ». Ils peuvent créer, modifier, publier et supprimer
LEURS PROPRES événements (event.event) depuis /my/events, sans aucun accès
au backend Odoo.

Sécurité : le contrôleur est la frontière — il vérifie l'appartenance au
groupe, agit en sudo avec une liste blanche de champs, et restreint chaque
opération aux événements dont l'utilisateur est l'organisateur
(organizer_user_id, fourni par social_events).
    """,
    "author": "Bemade",
    "license": "LGPL-3",
    "depends": ["social_events", "social_base", "website_event", "portal", "website"],
    "data": [
        'security/event_portal_security.xml',
        'security/ir.access.csv',
        'views/organiser_request_views.xml',
        'views/portal_templates.xml',
        'data/portal_entry_data.xml',
    ],
    "installable": True,
    "application": False,
}
