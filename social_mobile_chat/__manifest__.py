{
    'name': 'Social Mobile Chat',
    'version': '20.0.1.2.0',
    'category': 'Social / Communication',
    'summary': "Messagerie Discuss dans l'application mobile : conversations privées et de relation",
    'description': """
API de messagerie de l'application mobile, par-dessus Discuss (``social_messaging_discuss``) :

* conversations à deux (``chat``) et conversations de relation (``group`` de ``social_relation``) ;
* la politique de contact, le blocage et les pseudonymes de ``social_messaging_discuss`` s'appliquent ;
* messages texte et vocaux, lus et envoyés au nom du membre ; compteur de non-lus.
""",
    'author': 'Bemade',
    'license': 'LGPL-3',
    'depends': [
        'social_messaging_discuss',
        'social_mobile',
        'social_relation',
    ],
    'data': [],
    'installable': True,
}
