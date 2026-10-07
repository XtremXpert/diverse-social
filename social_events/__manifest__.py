{
    'name': 'Social Events',
    'version': '20.0.1.0.0',
    'category': 'Social',
    'summary': 'Community events with circle-based visibility — extends Odoo Event',
    'author': 'Bemade',
    'license': 'LGPL-3',
    'depends': ['event', 'social_circles'],
    'data': [
        'security/ir.access.csv',
        'security/security.xml',
        'views/event_ext_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
