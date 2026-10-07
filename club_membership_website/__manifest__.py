{
    'name': 'Club — Membership en ligne',
    'version': '20.0.1.0.0',
    'category': 'Club',
    'summary': "Public storefront for membership types, website_sale cart integration, member portal",
    'author': 'Bemade',
    'license': 'LGPL-3',
    'depends': [
        'club_membership_sale',
        'club_social_profile',
        'website_sale',
        'portal',
    ],
    'data': [
        'security/ir.access.csv',
        'data/website_menu.xml',
        'views/membership_website_templates.xml',
        'views/portal_templates.xml',
        'data/portal_entry_data.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
