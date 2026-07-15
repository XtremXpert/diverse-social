{
    'name': 'Social Safety — Quick Exit (camouflage MétéoMédia)',
    'version': '19.0.1.0.0',
    'category': 'Social',
    'summary': 'Bouton de sortie rapide + camouflage visuel (déguisement météo) '
               'sur les pages sensibles — module optionnel séparé de social_safety',
    'description': """
Social Safety — Quick Exit
==========================

Extrait de ``social_safety`` (2026-07-15) la seule fonction « bouton
panique » :

- Bouton ⏻ fixe (coin haut-gauche) sur toutes les pages portail, pour
  un utilisateur connecté : redirige instantanément vers un site neutre
  (MétéoMédia par défaut) via ``location.replace`` — pas de trace dans
  l'historique. Aussi déclenché par un double-appui sur Échap.
- Camouflage : sur les pages sensibles, remplace le titre d'onglet et le
  favicon (⛅ MétéoMédia par défaut) pour qu'un coup d'œil de loin ne
  révèle pas la nature du site.

Configurable via ``ir.config_parameter`` : ``social_safety.quick_exit_url``,
``social_safety.camouflage_title``, ``social_safety.camouflage_favicon``.

Module **feuille** : rien n'en dépend, il peut être installé ou
désinstallé sans cascade. ``social_safety`` (blocage, silencieux, mode
furtif, share-lockdown) reste indépendant et complet sans lui.
""",
    'author': 'Bemade',
    'license': 'LGPL-3',
    'depends': [
        'social_safety',
    ],
    'data': [
        'views/quick_exit.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
