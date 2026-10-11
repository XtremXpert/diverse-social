"""Run the full diverse setup on each upgrade.

Idempotent: each step skips work already done. See
diverse_club_social/hooks.py for the four concerns covered:
fr_CA install, website language config, menu translation,
menu gating.
"""
from odoo import api, SUPERUSER_ID

from odoo.addons.diverse_club_social.hooks import _apply_diverse_setup


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    _apply_diverse_setup(env)
