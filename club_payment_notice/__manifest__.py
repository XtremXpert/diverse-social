{
    'name': "Club — Avis de paiement à l'arrivée",
    'version': '20.0.1.0.0',
    'category': 'Club',
    'summary': "Affiche un avis de paiement en argent à l'arrivée sur les pages de paiement",
    'author': 'Bemade',
    'license': 'LGPL-3',
    'depends': [
        'website_sale',
        'website_event',
    ],
    'data': [
        'views/payment_notice_templates.xml',
    ],
    'installable': True,
    'auto_install': False,
}
