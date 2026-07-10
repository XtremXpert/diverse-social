{
    'name': 'Social Stealth — pseudonymes centralisés',
    'version': '19.0.1.0.0',
    'category': 'Social',
    'summary': "Un seul module en charge du remplacement du nom réel par le pseudonyme (stealth_name)",
    'description': """
Social Stealth
==============

Intercepte ``res.partner._compute_display_name`` pour que le pseudonyme
(``club_social_profile.profile.stealth_name``) remplace AUTOMATIQUEMENT le
vrai nom d'un membre partout où ``display_name`` est rendu (Many2one,
chatter, templates portail, courriels) — au lieu d'exiger que chaque module
pense à appeler ``_display_name_for_user()``.

Matrice spectateur (qui voit quoi) :

- le membre lui-même → vrai nom (il se reconnaît, ses factures sont justes) ;
- utilisateur interne (``base.group_user``) ou modérateur
  (``social_base.group_social_moderator``) → vrai nom (modération,
  comptabilité) ;
- tout autre spectateur (membre ordinaire, portail, public) → pseudonyme ;
- partner sans profil membre (organisme, municipalité) → jamais touché.

Échappatoires par contexte : ``with_context(stealth_display=False)`` force
le vrai nom (facturation, export privacy de ses propres données),
``=True`` force le pseudonyme.

Périmètre v1 — NE couvre PAS :

- les lectures directes de ``partner.name`` / ``user.name`` (le test de
  contrat de ce module balaie les pages clés pour attraper ces fuites) ;
- ``name_search`` (les surfaces de recherche membres — social_search,
  social_discovery, dropdowns de social_group/social_circles — portent
  déjà leur propre logique stealth) ;
- les contenus composés par cron sous OdooBot (interne → vrais noms) :
  le digest et les notifications passent par le helper explicite
  ``_display_name_for_user()``, qui reste la voie canonique hors requête.
""",
    'author': 'Bemade',
    'license': 'LGPL-3',
    'depends': [
        'club_social_profile',
        'social_base',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
