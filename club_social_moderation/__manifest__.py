{
    'name': 'Club Social Moderation',
    'version': '19.0.1.0.0',
    'category': 'Social',
    'summary': 'Bans, shadow bans and content reports for private clubs',
    'author': 'Bemade',
    'license': 'LGPL-3',
    'depends': [
        'club_social_profile',
    ],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/ir_cron.xml',
        'views/moderation_views.xml',
        'views/portal_templates.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
