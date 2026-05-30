{
    'name': 'City Club — Communauté municipale',
    'version': '19.0.1.0.0',
    'category': 'Social',
    'summary': "Socle pour réseau social municipal (vérification de résidence + activation d'adhésion)",
    'description': """
City Club
=========

Module générique pour décliner les modules sociaux (`social_*` / `club_social_*`)
en réseau social d'une communauté municipale ou de village.

Apporte :

- Champs de résidence sur ``club_social_profile.profile``
  (``residency_postal_code``, ``residency_state``, etc.)
- Helper de validation des codes postaux par configuration
- Action modérateur ``action_verify_residency()`` qui crée+active une
  ``club_membership.membership`` du type "résident" configuré (et donc
  accorde ``social_base.group_social_user`` via le workflow standard).
- Drapeau ``is_resident_default`` sur ``club_membership.type`` pour
  désigner le type par défaut à utiliser à l'approbation d'une résidence.

Les modules feuilles (ex: ``st_isidore_city_club``) fournissent la
configuration spécifique : nom de la ville, codes postaux autorisés,
centre géographique, et données démo (type de membership, groupes
locaux).
""",
    'author': 'Bemade',
    'license': 'LGPL-3',
    'depends': [
        'club_social_profile',
        'club_membership',
        'club_social_moderation',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/res_config_data.xml',
        'views/membership_type_views.xml',
        'views/profile_views.xml',
        'views/menus.xml',
        'views/residency_template.xml',
        'views/community_help_template.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
