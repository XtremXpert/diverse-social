{
    'name': 'Diverse — Club Social',
    'version': '20.0.1.0.22',
    'category': 'Social',
    'summary': 'Leaf module for www.diverse-cite.com — assembles all social modules with site-specific config',
    'author': 'Bemade',
    'license': 'LGPL-3',
    'depends': [
        # Club base
        'club_base',
        # Core social primitives
        'social_base',
        'social_feed',
        'social_story',
        'social_gallery',
        'social_group',
        'social_notifications',
        # Discovery & connections
        'social_circles',
        'social_discovery',
        'social_search',
        # Safety & consent
        'social_safety',
        'social_consent',
        'social_negotiation',
        'social_age_gate',
        # Governance & reputation
        'social_governance',
        'social_reputation',
        'social_analytics',
        # Club-specific
        'club_social_profile',
        'club_social_profile_bdsm',
        'club_social_moderation',
        'club_membership',
        'club_membership_sale',
        'club_membership_website',
        'social_onboarding',
        # Events
        'social_events',
        'social_calling',
        'club_event_user',
        'club_event_combo',
        'event_lodging',
        'club_payment_notice',
        # Privacy / Loi 25
        'social_privacy',
        # Mobile / PWA
        'social_pwa',
        # Push natif iPhone/Android via ntfy auto-hébergé
        'social_ntfy',
        # Public help page + community charter
        'social_help',
        # Messagerie Discuss (carte /my + entrée nav)
        'social_messaging_discuss',
        # Conversation de groupe de chaque groupe
        'social_group_discuss',
        # Website (homepage override)
        'website',
        'website_sale',
        'website_members_only',
        'diverse_website_members_only',
        # Accounting / sales (cartes portail /my/home à habiller d'icônes)
        'account',
        'account_payment',
        'sale',
        # Visual identity
        'theme_diverse_cite',
        # Favicon backend (res.company.favicon servi par web_favicon)
        'web_favicon',
    ],
    'data': [
        'security/ir.access.csv',
        'data/res_config_data.xml',
        'data/ir_cron.xml',
        'data/community_help_data.xml',
        'data/homepage_view.xml',
        'data/website_pages.xml',
        'data/view_names_fr.xml',
        'views/email_digest_template.xml',
        'views/mail_notification_layout.xml',
        'views/menus.xml',
        'views/community_hub.xml',
        'views/partners_page.xml',
        'views/hosting_page.xml',
        'views/portal_standard_icons.xml',
        'views/portal_dashboard_diverse.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
    'post_init_hook': 'post_init_hook',
}
