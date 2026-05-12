{
    'name': 'Club Social Profile',
    'version': '19.0.1.0.0',
    'category': 'Social',
    'summary': 'Member profiles, connections, and notifications for private clubs',
    'author': 'Bemade',
    'license': 'LGPL-3',
    'depends': [
        'social_base',
    ],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/profile_data.xml',
        'views/profile_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
