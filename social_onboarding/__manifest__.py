{
    'name': 'Club — Member Onboarding',
    'version': '20.0.1.0.0',
    'category': 'Social',
    'summary': "Guided profile completion flow for new members",
    'author': 'Bemade',
    'license': 'LGPL-3',
    'depends': [
        'club_social_profile',
        'club_membership',
        'portal',
    ],
    'data': [
        'security/ir.access.csv',
        'views/wizard_views.xml',
        'views/profile_views_ext.xml',
        'views/menus.xml',
        'views/portal_templates.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
