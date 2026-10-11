"""Réorganise la navigation website en 3 conteneurs équilibrés.

Crée le conteneur « Mon compte » et re-parente les menus :
- Galerie -> Communauté
- Profil BDSM / Parrainages / Adhésion / Sécurité / Consentement /
  Confidentialité -> Mon compte
+ corrige les séquences (NAV_LAYOUT). Sépare l'activité sociale (Mon réseau)
des réglages compte/sécurité (Mon compte). Aucun dropdown > 6 items.

100 % site-spécifique (pas de modif du submodule social) et idempotent :
on rejoue _apply_diverse_setup, déjà entièrement idempotent. Voir
diverse_club_social/hooks.py (_ensure_account_container, _reorganize_nav).
"""
from odoo import api, SUPERUSER_ID

from odoo.addons.diverse_club_social.hooks import _apply_diverse_setup


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    _apply_diverse_setup(env)
