{
    'name': 'Social Feed',
    'version': '20.0.2.0.1',
    'category': 'Social',
    'summary': "Fil d'actualité agrégé : posts, stories, événements, propositions, préférences + read state",
    'author': 'Bemade',
    'license': 'LGPL-3',
    'depends': [
        'club_social_profile',
        'social_safety',
        'social_circles',
        'social_group',
        'social_events',
        'social_base',
        'social_story',
        'social_governance',
        'social_gallery',
    ],
    'data': [
        'security/ir.access.csv',
        'data/cron.xml',
        'views/portal_transparency_templates.xml',
        'views/portal_feed.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'social_feed/static/src/js/feed_page.js',
            'social_feed/static/src/css/feed_page.css',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
}
