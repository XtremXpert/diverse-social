{
    'name': 'Social Reputation',
    'version': '19.0.1.0.0',
    'category': 'Social',
    'summary': 'Community vouching: members sponsor newcomers, creating a chain of accountability',
    'author': 'Bemade',
    'license': 'LGPL-3',
    'depends': [
        'club_social_profile',
        'portal',
        'social_discovery',
    ],
    'data': [
        'security/ir.model.access.csv',
        'security/security.xml',
        'data/website_menu.xml',
        'views/vouching_views.xml',
        'views/menus.xml',
        'views/portal_templates.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
}
