{
    'name': 'Social Nearby',
    'version': '20.0.1.0.0',
    'category': 'Social',
    'summary': "Grille de proximité de l'application mobile, sans jamais stocker de position exacte",
    'description': """
* l'application envoie sa position ; Odoo ne garde que la case d'environ 550 m qui la contient,
  une seule par membre, sans historique ;
* la grille liste les membres (et les relations visibles) les plus proches, avec une distance par
  paliers (« moins de 1 km », « 1 à 2 km »…) : impossible de retrouver une position par trilatération ;
* elle respecte la visibilité des profils, les cercles, les blocages et les bannissements.
""",
    'author': 'Bemade',
    'license': 'LGPL-3',
    'depends': [
        'club_social_moderation',
        'social_circles',
        'social_mobile',
        'social_relation',
        'social_safety',
    ],
    'data': [
        'security/ir.access.csv',
        'data/cron.xml',
    ],
    'installable': True,
}
