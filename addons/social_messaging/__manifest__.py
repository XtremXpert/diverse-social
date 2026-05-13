{
    'name': 'Social Messaging',
    'version': '19.0.1.0.0',
    'category': 'Social',
    'summary': 'Private direct messaging between users',
    'author': 'Bemade, Odoo Community Association (OCA)',
    'website': 'https://github.com/OCA/social',
    'license': 'LGPL-3',
    'depends': [
        'social_base',
        'social_safety',
    ],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'views/messaging_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
