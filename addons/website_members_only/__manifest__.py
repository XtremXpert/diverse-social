{
    'name': 'Website Members Only',
    'summary': 'Cache les événements aux visiteurs non connectés',
    'version': '19.0.1.0.0',
    'category': 'Website',
    'depends': ['website_event'],
    'data': [
        'views/res_config_settings_views.xml',
    ],
    'post_init_hook': '_post_init_hook',
    'author': 'Bemade',
    'license': 'LGPL-3',
}
