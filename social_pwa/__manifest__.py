{
    'name': 'Social PWA',
    'version': '19.0.1.1.0',
    'category': 'Social',
    'summary': 'Progressive Web App: installable home screen icon, offline shell, generic-payload push',
    'description': """
        Push notifications require pywebpush to actually deliver — the
        push service in models/push_service.py soft-imports it and
        silently no-ops if missing, so the rest of the module (manifest,
        service worker, install button) still works without the pip
        package. Production deployments that want push need to install
        pywebpush separately.
    """,
    'author': 'Bemade',
    'license': 'LGPL-3',
    'depends': [
        'web',
        'portal',
        'club_social_profile',
    ],
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
