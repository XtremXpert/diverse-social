{
    'name': "Club — Inscription événement par membre",
    'version': '20.0.2.0.0',
    'category': 'Club',
    'summary': "Restreint les inscriptions aux res.users et affiche le login partout",
    'author': 'Bemade',
    'license': 'LGPL-3',
    'depends': [
        'website_event',
    ],
    'data': [
        'views/event_ticket_views.xml',
        'views/event_registration_templates.xml',
    ],
    'installable': True,
    'auto_install': False,
    'demo': [],
    'test': [],
}
