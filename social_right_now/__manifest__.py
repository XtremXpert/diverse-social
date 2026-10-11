{
    'name': 'Social — Disponible maintenant',
    'version': '20.0.1.0.0',
    'category': 'Social / Communication',
    'summary': "Sessions « Disponible maintenant » — seul canal de contact hors "
               "connexions, groupes et cercles",
    'description': """
Inspiré du « Right Now » de Grindr, adapté à la philosophie consentement du site.

Une personne se déclare « disponible » pour 1 h / 2 h / 4 h (renouvelable). Pendant
la session, elle apparaît sur le tableau /right-now (visible par tous les membres)
et devient l'unique exception à la politique de contact (cf. social_messaging_discuss
Phase 1) : n'importe quel membre peut lui écrire, même sans connexion.

Éphémère : à l'expiration, les conversations nées de la session se ferment (plus
d'écriture) sauf si une connexion acceptée existe désormais entre les deux. Le
contenu n'est pas supprimé (modération possible).

Aucune donnée de présence temps réel permanente : la session est explicite,
bornée dans le temps, et l'utilisateur peut la couper à tout moment.
    """,
    'author': 'Bemade',
    'license': 'LGPL-3',
    'depends': [
        'social_messaging_discuss',   # hook _smd_message_exception + discuss.channel
        'club_social_profile',        # profil, stealth_name, avatar
        'social_safety',              # blocage + panic mode
        'social_notifications',       # notifications in-app + bus
    ],
    'data': [
        'security/ir.access.csv',
        'data/cron.xml',
        'data/website_menu.xml',
        'views/right_now_templates.xml',
        'views/right_now_backend_views.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'social_right_now/static/src/js/right_now.js',
        ],
    },
    'installable': True,
    'application': False,
}
