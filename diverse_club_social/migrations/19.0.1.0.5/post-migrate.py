"""Open the Contact Us menu + re-apply the Diverse-Cité visual identity.

Two fixes bundled here:

1. `_restrict_member_menus` is additive and never removed group_social_user,
   so /contactus stayed gated even though it's listed in PUBLIC_URLS.
   `_open_contact_menu` strips the group from that single menu.

2. `_apply_logo` now also writes res.company.favicon (used by web_favicon
   in backend/no-website contexts), fixing the stale "multi-media" favicon.

Running the full idempotent setup keeps every concern in sync. See
diverse_club_social/hooks.py.
"""
from odoo import api, SUPERUSER_ID

from odoo.addons.diverse_club_social.hooks import _apply_diverse_setup


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    _apply_diverse_setup(env)
