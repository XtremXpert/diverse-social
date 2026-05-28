{
    'name': 'Social PWA',
    'version': '19.0.1.0.0',
    'category': 'Social',
    'summary': 'Progressive Web App: installable home screen icon, offline shell, generic-payload push',
    'author': 'Bemade',
    'license': 'LGPL-3',
    'depends': [
        'web',
        'portal',
        'club_social_profile',
    ],
    'external_dependencies': {
        'python': ['pywebpush'],
    },
    'data': [
        'security/ir.model.access.csv',
        'data/ir_config_parameter.xml',
        'views/pwa_meta.xml',
        'views/pwa_install_button.xml',
        'views/pwa_offline.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'social_pwa/static/src/js/pwa_register.js',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
}
