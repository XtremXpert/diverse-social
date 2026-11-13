{
    'name': 'Social Meet',
    'version': '20.0.1.0.0',
    'category': 'Social',
    'summary': "Rencontres spontanées et planifiées de l'application mobile",
    'description': """
Un seul objet « rencontre », deux vitesses :

* **spontanée** (``kind = now``) : visible pendant quelques heures, lieu approché
  (case d'environ 550 m) ou Safe Zone, join libre, expiration automatique ;
* **planifiée** (``kind = planned``) : fenêtre à l'avance, inscription avec
  approbation facultative de l'hôte, enrobage d'un ``event.event`` pour hériter
  de la page web, des places et de la billetterie.

Dans les deux cas la rencontre accepte **plusieurs participants** et se dote
d'un fil de discussion (``discuss.channel`` de type ``meet``, branché par
``social_mobile_chat``).

Contrat : ``docs/spec-rencontres.md`` du dépôt diverse-odoo.
""",
    'author': 'Bemadé / Diverse-Cité',
    'license': 'LGPL-3',
    'depends': [
        'mail',
        'event',
        'social_mobile',
        'social_base',
        'social_circles',
        'social_safety',
        'social_relation',
        'social_nearby',
        'club_social_profile',
    ],
    'data': [
        'security/ir.access.csv',
        'data/cron.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
