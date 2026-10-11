{
    'name': 'Social Messaging — Discuss (A/B)',
    'version': '20.0.2.1.0',
    'category': 'Social / Communication',
    'summary': "Messagerie privée via Discuss natif — test A/B vs social_messaging",
    'author': 'Bemade',
    'license': 'LGPL-3',
    # NB : pas de dépendance à social_messaging — coexistence sans couplage, pour
    # faciliter sa désinstallation au cutover. On unifie sur discuss.channel : le
    # MÊME canal entre 2 personnes sert au chat ET aux appels (social_calling_discuss).
    'depends': [
        'mail',                  # discuss.channel + route publique /discuss/channel/<id>
        'social_safety',         # social_safety.block — enforcement du blocage
        'club_social_profile',   # profil portail (bouton + avatars/stealth_name)
        'portal',                # portal.portal_layout + portal_my_home
        'website',               # website.menu (entrée de navigation top)
    ],
    'data': [
        'data/website_menu.xml',
        'views/portal_chats.xml',
        'views/message_button.xml',
        'views/discuss_public_nav.xml',
        'views/res_config_settings_views.xml',
        'data/portal_entry_data.xml',
    ],
    # GAPS CONNUS (phase A/B — à traiter au cutover) :
    #  - social_notifications écoute social_messaging.message, PAS les messages
    #    Discuss → pas de notif "cloche" custom pour les messages Discuss.
    #  - social_privacy (Loi 25) n'exporte/anonymise PAS les mail.message Discuss
    #    → gap conformité bloquant pour le cutover, acceptable en test A/B.
    #  - UX : /discuss/channel/<id> = client Discuss autonome (look app), tandis
    #    que /my/chats est au look portail.
    'installable': True,
    'application': False,
    'auto_install': False,
}
