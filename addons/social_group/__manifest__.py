{
    'name': 'Social Groups',
    'version': '19.0.1.0.0',
    'category': 'Social',
    'summary': 'Groups and communities for social networks',
    'author': 'Bemade, Odoo Community Association (OCA)',
    'website': 'https://github.com/OCA/social',
    'license': 'LGPL-3',
    'depends': [
        'social_base',
    ],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/ir_cron.xml',
        'views/group_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
