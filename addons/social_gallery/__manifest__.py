{
    'name': 'Social Gallery',
    'version': '19.0.1.0.0',
    'category': 'Social',
    'summary': 'Photo and video galleries for social networks',
    'author': 'Bemade, Odoo Community Association (OCA)',
    'website': 'https://github.com/OCA/social',
    'license': 'LGPL-3',
    'depends': [
        'social_base',
        'portal',
    ],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'views/gallery_views.xml',
        'views/portal_templates.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
