{
    'name': 'Social Mobile Call',
    'version': '20.0.1.0.0',
    'category': 'Social / Communication',
    'summary': "Appels audio Discuss dans l'application mobile, par le SFU d'Odoo",
    'description': """
API d'appel de l'application mobile, par-dessus les appels Discuss :

* rejoindre, maintenir, quitter ou refuser l'appel d'une conversation mobile ;
* l'application rejoint toujours par le SFU d'Odoo (serveur média), dès deux participants ;
* un appel déjà passé par le SFU y reste quand d'autres participants le rejoignent depuis le site.
""",
    'author': 'Bemade',
    'license': 'LGPL-3',
    'depends': [
        'social_mobile_chat',
    ],
    'data': [],
    'installable': True,
}
