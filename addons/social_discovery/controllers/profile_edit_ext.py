from odoo.http import request, route

from odoo.addons.club_social_profile.controllers.portal_edit import ProfileEditPortal


class ProfileEditPortalDiscovery(ProfileEditPortal):
    """Adds the show_on_map opt-in toggle to the preferences POST."""

    @route()
    def save_profile_preferences(self, **kw):
        profile = self._get_own_profile()
        # HTML checkboxes only submit a value when checked, so absence = False.
        show_on_map = bool(request.httprequest.form.get('show_on_map'))
        profile.write({'show_on_map': show_on_map})
        return super().save_profile_preferences(**kw)
