{
    'name': 'Club — Adhésion en ligne',
    'version': '19.0.1.0.0',
    'category': 'Club',
    'summary': "Vitrine publique des types d'adhésion, intégration panier website_sale, portail membre",
    'author': 'Bemade',
    'license': 'LGPL-3',
    'depends': [
        'club_membership_sale',
        'club_social_profile',
        'website_sale',
        'portal',
    ],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/website_menu.xml',
        'views/membership_website_templates.xml',
        'views/portal_templates.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
