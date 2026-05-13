{
    'name': 'Social Circles',
    'version': '19.0.1.0.0',
    'category': 'Social',
    'summary': 'Trust circles: organise your connections into named tiers and gate profile sections accordingly',
    'author': 'Bemade',
    'license': 'LGPL-3',
    'depends': [
        'club_social_profile',
        'portal',
    ],
    'data': [
        'security/ir.model.access.csv',
        'security/security.xml',
        'views/circle_views.xml',
        'views/menus.xml',
        'views/portal_templates.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
