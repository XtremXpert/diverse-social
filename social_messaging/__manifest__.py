{
    'name': 'Social Messaging (retiré)',
    'version': '19.0.1.0.0',
    'category': 'Social',
    'summary': 'Private direct messaging between users — RETIRÉ au profit de Discuss (social_messaging_discuss)',
    'author': 'Bemade, Odoo Community Association (OCA)',
    'website': 'https://github.com/OCA/social',
    'license': 'LGPL-3',
    'depends': [
        'social_base',
        'social_safety',
        'portal',
        'club_social_profile',
    ],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/website_menu.xml',
        'views/messaging_views.xml',
        'views/portal_messaging.xml',
    ],
    # Retiré au profit de Discuss (social_messaging_discuss). Désinstallé en
    # prod ; plus aucun module n'en dépend. Non installable pour le sortir de
    # l'install/test CI et éviter le conflit de double-replace du bouton Message.
    'installable': False,
    'application': False,
    'auto_install': False,
}
