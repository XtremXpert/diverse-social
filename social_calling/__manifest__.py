{
    'name': 'Social Calling',
    'version': '20.0.2.0.1',
    'category': 'Social / Communication',
    'summary': "Sonnerie d'appel entrant et présence sur le portail",
    'author': 'Bemade',
    'license': 'LGPL-3',
    'depends': [
        'club_social_profile',
        'social_safety',
        'social_notifications',
        'portal',
    ],
    'data': [
        'data/cleanup.xml',
        'views/incoming_call.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
