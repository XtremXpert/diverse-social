from odoo.http import request, route

from odoo.addons.club_social_profile.controllers.portal_edit import ProfileEditPortal


class ProfileEditPortalDiscovery(ProfileEditPortal):
    """Adds the social_discovery opt-in/out toggles to the preferences POST.

    Two distinct semantics on the same form:
    - show_on_map: opt-in. Default False. HTML "checkbox absent" → False
      both for a deliberate untick and for the very first submit on an
      account that predates the feature. That's safe because the default
      is False either way.
    - show_in_suggestions: opt-out. Default True. We cannot conflate
      "untick" with "first submit" here — doing so would silently
      opt every legacy account out. We require the form to carry a
      hidden `show_in_suggestions_present` marker (added by the template
      we control) before honouring an untick.
    """

    @route()
    def save_profile_preferences(self, **kw):
        profile = self._get_own_profile()
        form = request.httprequest.form
        vals = {}
        # show_on_map (opt-in, default False)
        vals['show_on_map'] = bool(form.get('show_on_map'))
        # show_in_suggestions (opt-out, default True) — only write when the
        # form actually carried our toggle, so legacy callers don't flip it.
        if form.get('show_in_suggestions_present'):
            vals['show_in_suggestions'] = bool(form.get('show_in_suggestions'))
        if vals:
            profile.write(vals)
        return super().save_profile_preferences(**kw)
