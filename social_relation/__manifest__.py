{
    'name': 'Social Relations',
    'version': '20.0.1.0.1',
    'category': 'Social',
    'summary': "Relations de deux personnes ou plus (couple, trouple, polycule), chacune avec son profil",
    'description': """
Une relation réunit deux membres ou plus. Chaque membre garde son compte, peut rencontrer seul,
et peut faire partie de plusieurs relations.

* entrée sur invitation, approuvée par tous les membres déjà présents, puis acceptée par l'invité ;
* visible des autres membres seulement si tous ses membres l'acceptent ;
* conversation de groupe Discuss réservée à ses membres ;
* crée elle-même les relations à deux (``res.partner.relation``) entre ses membres : les cercles
  « Partenaires » et les règles de visibilité existantes continuent de fonctionner.
""",
    'author': 'Bemade',
    'license': 'LGPL-3',
    'depends': [
        'mail',
        'social_circles',
        'social_mobile',
        'social_safety',
    ],
    'data': [
        'security/ir.access.csv',
        'views/relation_views.xml',
    ],
    'installable': True,
}
