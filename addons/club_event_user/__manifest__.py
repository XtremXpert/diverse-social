{
    'name': "Club — Inscription événement par membre",
    'version': '19.0.1.0.0',
    'category': 'Club',
    'summary': "Restreint les inscriptions aux res.users et affiche le login partout",
    'author': 'Bemade',
    'license': 'LGPL-3',
    'depends': [
        'website_event',
    ],
    'data': [
        'views/event_registration_templates.xml',
    ],
    'installable': True,
    'auto_install': False,
}
