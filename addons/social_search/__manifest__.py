{
    'name': 'Social Search',
    'version': '19.0.1.0.0',
    'category': 'Social',
    'summary': 'Recherche unifiée membres/groupes/événements/posts avec respect de la visibilité',
    'author': 'Bemade',
    'license': 'LGPL-3',
    'depends': [
        'club_social_profile',
        'social_gallery',
        'social_safety',
        'social_group',
        'social_events',
        'social_base',
    ],
    'data': [
        'security/ir.model.access.csv',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
