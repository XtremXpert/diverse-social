{
    'name': 'Social Calling — Discuss (A/B)',
    'version': '20.0.1.0.1',
    'category': 'Social / Communication',
    'summary': "Variante d'appel via Discuss natif (WebRTC) — pour test A/B vs Jitsi",
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
    'installable': True,
    'application': False,
    'auto_install': False,
}
