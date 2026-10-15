{
    'name': 'Social Mobile',
    'version': '20.0.1.2.0',
    'category': 'Social',
    'summary': "API de l'application mobile : inscription par QR code et parrainage en personne",
    'description': """
Application mobile du réseau social (iOS) :

* le nouveau venu saisit son courriel, puis son application n'affiche qu'un QR code renouvelé
  toutes les 30 secondes ;
* un membre actif le scanne dans son application : le compte est créé, le parrainage
  (``social_reputation.vouching``, chaîne de confiance) aussi, et l'adhésion est activée ;
* l'application reçoit alors une clé API de portée « social_mobile », qui n'ouvre que
  ``/api/social/v1``.

Contrat de l'API : README.md.
""",
    'author': 'Bemade',
    'license': 'LGPL-3',
    'depends': [
        'club_membership',
        'club_social_moderation',
        'social_privacy',
        'social_reputation',
    ],
    'data': [
        'security/ir.access.csv',
        'data/cron.xml',
        'views/enrollment_views.xml',
        'views/res_config_settings_views.xml',
    ],
    'installable': True,
}
