{
    'name': 'Club — Intégration membres',
    'version': '19.0.1.0.0',
    'category': 'Social',
    'summary': "Parcours guidé de complétion de profil pour les nouveaux membres",
    'author': 'Bemade',
    'license': 'LGPL-3',
    'depends': [
        'club_social_profile',
        'club_membership',
        'portal',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/wizard_views.xml',
        'views/profile_views_ext.xml',
        'views/menus.xml',
        'views/portal_templates.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
