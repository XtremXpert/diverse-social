{
    'name': 'Website Blog — Accès restreint',
    'summary': 'Limite la visibilité d\'un blog à des utilisateurs Odoo spécifiques',
    'version': '19.0.2.0.0',
    'category': 'Website',
    'depends': ['website_blog', 'club_visibility'],
    'data': [
        'views/blog_blog_views.xml',
        'views/website_blog_templates.xml',
    ],
    'installable': True,
    'author': 'Bemade',
    'license': 'LGPL-3',
}
