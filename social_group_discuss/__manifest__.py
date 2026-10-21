{
    'name': 'Social Groups — Discuss',
    'version': '20.0.1.0.0',
    'category': 'Social / Communication',
    'summary': "Chaque groupe a sa conversation de groupe Discuss, aux mêmes membres",
    'author': 'Bemade',
    'license': 'LGPL-3',
    'depends': [
        'mail',
        'social_group',
    ],
    'data': [
        'views/portal_templates.xml',
    ],
    'post_init_hook': '_post_init_hook',
    'installable': True,
    'application': False,
    'auto_install': False,
}
