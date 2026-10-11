"""Re-apply diverse setup on each upgrade past 1.0.2.

Idempotent. See diverse_club_social/hooks.py — adds logo application
to the four previous concerns (fr_CA install, website language config,
menu translation, menu gating).
"""
from odoo import api, SUPERUSER_ID

from odoo.addons.diverse_club_social.hooks import _apply_diverse_setup


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    _apply_diverse_setup(env)
