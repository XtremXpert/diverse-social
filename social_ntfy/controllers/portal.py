from odoo.addons.club_social_profile.controllers.portal_edit import ProfileEditPortal
from odoo.http import request, route


class NtfyProfilePortal(ProfileEditPortal):

    @route('/my/profile/edit', auth='user', website=True, sitemap=False)
    def edit(self, section='identity', **kw):
        # Lazily provision the member's secret topic the first time they open
        # the profile editor, so the ntfy subscription section can display it.
        self._get_own_profile()._ensure_ntfy_topic()
        return super().edit(section=section, **kw)

    @route('/my/ntfy/regenerate', auth='user', methods=['POST'], website=True, csrf=True)
    def ntfy_regenerate(self, **kw):
        self._get_own_profile().action_regenerate_ntfy_topic()
        return request.redirect('/my/profile/edit?section=preferences')
