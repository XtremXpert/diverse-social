{
    'name': 'Social Discovery',
    'version': '19.0.1.0.0',
    'category': 'Social',
    'summary': 'Consensual profile discovery: you search, not the algorithm',
    'author': 'Bemade',
    'license': 'LGPL-3',
    'depends': [
        'club_social_profile',
        'social_circles',
        'portal',
    ],
    'data': [
        'security/ir.model.access.csv',
        'security/security.xml',
        'data/values.xml',
        'views/criteria_views.xml',
        'views/menus.xml',
        'views/portal_members.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
}
