{
    'name': 'Événement — Hébergement',
    'summary': 'Forfaits hébergement (lit simple/double) liés aux billets d\'événement',
    'version': '20.0.1.0.0',
    'category': 'Events',
    'depends': ['website_event_sale'],
    'data': [
        'views/event_ticket_views.xml',
        'views/event_registration_views.xml',
        'views/event_event_views.xml',
        'views/event_lodging_templates.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'event_lodging/static/src/js/event_lodging.js',
        ],
    },
    'installable': True,
    'test': ['tests/test_event_lodging.py'],
    'author': 'Bemade',
    'license': 'LGPL-3',
}
