{
    'name': "Club l'Orage — Club Social",
    'version': '19.0.1.0.0',
    'category': 'Social',
    'summary': "Leaf module for orage.club — assembles social modules with l'Orage-specific config",
    'author': 'Bemade',
    'license': 'LGPL-3',
    'depends': [
        'social_base',
        'social_group',
        'social_story',
        'social_gallery',
        'social_messaging',
        'club_social_profile',
        'club_social_moderation',
        # club_social_profile_bdsm is NOT a dependency here — l'Orage may not use BDSM profiles
    ],
    'data': [
        'data/res_config_data.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
}
