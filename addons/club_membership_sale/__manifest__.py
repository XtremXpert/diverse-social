{
    'name': 'Club — Adhésion via vente',
    'version': '19.0.1.0.0',
    'category': 'Club',
    'summary': "Activation automatique des adhésions à la confirmation de commande et au paiement",
    'author': 'Bemade',
    'license': 'LGPL-3',
    'depends': [
        'club_membership',
        'sale',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/membership_product_data.xml',
        'views/product_template_views.xml',
        'views/sale_order_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
