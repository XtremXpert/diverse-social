{
    'name': 'Social Consent',
    'version': '20.0.1.0.0',
    'category': 'Social',
    'summary': 'Consent-first access control: define a gate visitors must pass before contacting you',
    'author': 'Bemade',
    'license': 'LGPL-3',
    'depends': [
        'social_base',
        'club_social_profile',
    ],
    'data': [
        'security/ir.access.csv',
        'data/website_menu.xml',
        'views/portal_templates.xml',
        'views/gate_views.xml',
        'views/request_views.xml',
        'views/menus.xml',
        'data/portal_entry_data.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
