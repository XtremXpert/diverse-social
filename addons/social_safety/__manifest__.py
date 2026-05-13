{
    'name': 'Social Safety',
    'version': '19.0.1.0.0',
    'category': 'Social',
    'summary': 'Block, mute, and panic mode — personal safety controls',
    'author': 'Bemade',
    'license': 'LGPL-3',
    'depends': [
        'club_social_profile',
        'social_discovery',
    ],
    'data': [
        'security/ir.model.access.csv',
        'security/security.xml',
        'views/block_views.xml',
        'views/mute_views.xml',
        'views/menus.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
