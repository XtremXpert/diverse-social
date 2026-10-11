{
    'name': 'Social Calling',
    'version': '20.0.1.0.0',
    'category': 'Social / Communication',
    'summary': 'One-to-one video and audio calls via Jitsi Meet integration',
    'author': 'Bemade',
    'license': 'LGPL-3',
    'depends': [
        'club_social_profile',
        'social_safety',
        'social_notifications',
        'portal',
    ],
    'data': [
        'security/ir.access.csv',
        'data/ir_sequence.xml',
        'views/incoming_call.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
