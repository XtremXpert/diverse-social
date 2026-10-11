{
    'name': 'Social Age Gate — 18+ Verification',
    'version': '20.0.1.0.0',
    'category': 'Social',
    'summary': 'Mandatory 18+ gate before accessing the private social network.',
    'author': 'Bemade',
    'license': 'LGPL-3',
    'depends': ['social_onboarding'],
    'data': [
        'views/portal_age_gate.xml',
        'views/wizard_age_gate.xml',
    ],
    'installable': True,
    'auto_install': False,
    'post_init_hook': 'post_init_hook',
}
