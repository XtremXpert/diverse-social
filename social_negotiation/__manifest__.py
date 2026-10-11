{
    'name': 'Social Negotiation',
    'version': '20.0.1.0.0',
    'category': 'Social',
    'summary': 'Co-authored negotiation documents: shared limits, desires, safeguards and co-signatures',
    'author': 'Bemade',
    'license': 'LGPL-3',
    'depends': [
        'club_social_profile',
        'portal',
    ],
    'data': [
        'security/ir.access.csv',
        'data/website_menu.xml',
        'views/negotiation_views.xml',
        'views/menus.xml',
        'views/portal_templates.xml',
        'data/portal_entry_data.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
