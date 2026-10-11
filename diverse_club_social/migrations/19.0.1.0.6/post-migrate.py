"""Repair websites whose top-nav root (website.menu_id) is empty.

The social leaf menus ended up at website_id=<site> while their container/root
menus stayed website_id=False, so website._compute_menu found no parent-less
owned menu → website.menu_id was False → the whole top nav rendered empty for
everyone. _ensure_website_menu_root adopts the generic menu tree into the
website so a root exists again.

Calls only the repair (not the full _apply_diverse_setup) so the existing menu
gating — which differs between prod and a fresh install — is left untouched.
See diverse_club_social/hooks.py.
"""
from odoo import api, SUPERUSER_ID

from odoo.addons.diverse_club_social.hooks import _ensure_website_menu_root


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    _ensure_website_menu_root(env)
