{
    'name': 'Social Base',
    'version': '20.0.1.0.1',
    'category': 'Social',
    'summary': 'Core social network primitives: posts, comments, reactions',
    'author': 'Bemade, Odoo Community Association (OCA)',
    'website': 'https://github.com/OCA/social',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'mail',
        'portal',
        'website',
    ],
    'data': [
        'security/security.xml',
        'security/ir.access.csv',
        'views/post_views.xml',
    ],
    'assets': {
        'web.assets_frontend': [],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
}
