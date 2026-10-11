{
    'name': 'Club Social Profile — BDSM',
    'version': '20.0.1.0.0',
    'category': 'Social',
    'summary': 'BDSM-specific profile fields, kinks and compatibility scoring',
    'author': 'Bemade',
    'license': 'LGPL-3',
    'depends': [
        'club_social_profile',
        'portal',
    ],
    'data': [
        'security/ir.access.csv',
        'data/kink_data.xml',
        'data/website_menu.xml',
        'views/bdsm_views.xml',
        'views/portal_templates.xml',
        'views/portal_profile_bdsm_inject.xml',
        'data/portal_entry_data.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
