"""Re-apply menu restrictions on each upgrade.

Idempotent: only adds group_social_user where it's missing.
See diverse_club_social/hooks.py for the URL-based gating logic.
"""
from odoo import api, SUPERUSER_ID

from odoo.addons.diverse_club_social.hooks import _restrict_member_menus


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    _restrict_member_menus(env)
