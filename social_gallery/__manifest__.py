{
    'name': 'Social Gallery',
    'version': '20.0.2.2.0',
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
        'security/ir.access.csv',
        'data/website_menu.xml',
        'views/gallery_views.xml',
        'views/portal_templates.xml',
        'data/portal_entry_data.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
