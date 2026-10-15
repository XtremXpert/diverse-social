{
    'name': 'Social PWA',
    'version': '20.0.2.1.0',
    'category': 'Social',
    'summary': 'Progressive Web App: installable home screen icon, offline shell, generic-payload push',
    'description': """
        Push delivery rides on the standard mail.push queue + cron
        (devices in mail.push.device, VAPID keys auto-generated) — no
        pywebpush dependency. The payload stays a constant camouflaged
        title/body: never route our notifications through the
        mail.message web-push path, which would put message content on
        the lock screen.
    """,
    'author': 'Bemade',
    'license': 'LGPL-3',
    'depends': [
        'web',
        'portal',
        'mail',
        'club_social_profile',
    ],
    'data': [
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
