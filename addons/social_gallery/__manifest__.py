{
    'name': 'Social Gallery',
    'version': '19.0.2.1.0',
    'category': 'Social',
    'summary': 'Photo and video galleries for social networks',
    'author': 'Bemade, Odoo Community Association (OCA)',
    'website': 'https://github.com/OCA/social',
    'license': 'LGPL-3',
    'depends': [
        'social_base',
        'club_social_profile',
        'portal',
    ],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/website_menu.xml',
        'views/gallery_views.xml',
        'views/portal_templates.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
}
