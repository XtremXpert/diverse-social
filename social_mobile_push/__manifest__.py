{
    'name': 'Social Mobile Push',
    'version': '20.0.1.4.0',
    'category': 'Social / Communication',
    'summary': "Notifications iPhone natives (APNs) de l'application mobile",
    'description': """
Notifications iPhone natives, envoyées directement à Apple (APNs, jeton .p8) :

* nouveau message dans une conversation à deux ou de relation ;
* invitation dans une relation, proposition à approuver.

Contenu discret par défaut (« Nouveau message », sans nom ni texte). Envoi par une file d'attente
traitée par une tâche planifiée déclenchée aussitôt : l'envoi ne ralentit jamais la requête.
Les copies de la base (staging) sont neutralisées : clé APNs effacée, appareils désactivés.
""",
    'author': 'Bemade',
    'license': 'LGPL-3',
    'depends': [
        'social_mobile_chat',
        'social_relation',
    ],
    'external_dependencies': {'python': ['httpx', 'h2']},
    'data': [
        'security/ir.access.csv',
        'data/cron.xml',
        'views/res_config_settings_views.xml',
        'views/device_views.xml',
        'views/test_push_views.xml',
    ],
    'installable': True,
}
