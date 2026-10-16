{
    'name': 'Social Calling — Discuss',
    'version': '20.0.1.0.3',
    'category': 'Social / Communication',
    'summary': "Appels entre membres par Discuss natif (WebRTC)",
    'author': 'Bemade',
    'license': 'LGPL-3',
    'depends': [
        'social_calling',        # plomberie partagée : incoming_call.js, bus
        'mail',
        'club_social_profile',   # vue profil portail (point d'injection bouton)
    ],
    'data': [
        'data/ice_servers.xml',
        'views/call_button.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'social_calling_discuss/static/src/js/rtc_frontend_patch.js',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
}
