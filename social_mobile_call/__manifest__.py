{
    'name': 'Social Mobile Call',
    'version': '20.0.1.3.0',
    'category': 'Social / Communication',
    'summary': "Appels audio Discuss dans l'application mobile, par le SFU d'Odoo",
    'description': """
API d'appel de l'application mobile, par-dessus les appels Discuss :

* rejoindre, maintenir, quitter ou refuser l'appel d'une conversation mobile ;
* l'application rejoint toujours par le SFU d'Odoo (serveur média), dès deux participants ;
* un appel déjà passé par le SFU y reste quand d'autres participants le rejoignent depuis le site ;
* l'appel sonne sur l'iPhone même application fermée (notification VoIP, CallKit).
""",
    'author': 'Bemade',
    'license': 'LGPL-3',
    'depends': [
        'social_mobile_chat',
        'social_mobile_push',
        'social_calling_discuss',  # fin de l'appel quand il ne reste qu'une personne
    ],
    'data': [],
    'installable': True,
}
