{
    'name': 'St-Isidore-de-Beauce — Réseau citoyen',
    'version': '19.0.1.0.0',
    'category': 'Social',
    'summary': "Leaf module — assemble city_club + modules social_* pour la communauté de St-Isidore-de-Beauce (G0S 2S0)",
    'description': """
Réseau social privé pour la communauté de St-Isidore-de-Beauce.

Alternative locale à Facebook pour les résidents :

- Inscription ouverte avec vérification de résidence (code postal G0S)
- Adhésion gratuite à vie (``Résident de St-Isidore``) approuvée par
  les modérateurs.
- Groupes thématiques : loisirs, école, fabrique, brigade incendie,
  petites annonces, entraide.
- Discovery géographique centrée sur le village.
- Gouvernance citoyenne (propositions + votes).
- PWA + notifications push.
- Conforme à la Loi 25 (privacy_consent).
""",
    'author': 'Bemade',
    'license': 'LGPL-3',
    'depends': [
        # Socle Club + City
        'club_base',
        'city_club',
        # Identité, adhésion (sans paiement)
        'club_social_profile',
        'club_social_moderation',
        'club_membership',
        # Primitives sociales
        'social_base',
        'social_feed',
        'social_search',
        # Contenu communautaire
        'social_group',
        'social_story',
        'social_gallery',
        'social_post_categories',
        # Communication
        'social_messaging',
        'social_notifications',
        # Sécurité & confidentialité
        'social_safety',
        'social_circles',
        'social_privacy',
        # Évènements + discovery
        'social_events',
        'social_discovery',
        'club_event_user',
        # Gouvernance citoyenne
        'social_governance',
        # Outils modérateur + onboarding
        'social_analytics',
        'social_onboarding',
        # Mobile
        'social_pwa',
    ],
    'data': [
        'data/res_config_data.xml',
        'data/membership_type_data.xml',
        'data/post_categories_data.xml',
        'views/menus.xml',
    ],
    'demo': [
        'data/demo_groups.xml',
        'data/demo_events.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
}
