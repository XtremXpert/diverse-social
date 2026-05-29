from odoo.http import request

from odoo.addons.web.controllers.home import Home

_RESIDENCY_REDIRECT = '/residency/verify'


class CityClubHome(Home):

    def _login_redirect(self, uid, redirect=None):
        """Redirect un-verified residents to the residency form.

        Skips the redirect when:
        - the user has ``group_social_user`` (already member) ;
        - the user is staff (internal — admin, moderator) ;
        - an explicit ``redirect`` was requested by the caller ;
        - no profile exists yet (failsafe — should not happen since the
          profile is created on the controller's first hit).

        We don't override the destination for users who reach the residency
        page after submitting — the page itself renders the right banner
        based on residency_state.
        """
        if redirect:
            return super()._login_redirect(uid, redirect=redirect)

        user = request.env['res.users'].sudo().browse(uid)

        # Staff bypass the gate: admins reach Settings, moderators reach the
        # pending-residency queue. They aren't community residents.
        if user.has_group('social_base.group_social_moderator') \
                or user.has_group('base.group_system'):
            return super()._login_redirect(uid, redirect=redirect)

        # Already a member — let the standard flow land them on /odoo or
        # whatever the default is.
        if user.has_group('social_base.group_social_user'):
            return super()._login_redirect(uid, redirect=redirect)

        Profile = request.env['club_social_profile.profile'].sudo()
        profile = Profile.search([('user_id', '=', uid)], limit=1)
        if profile and profile.residency_state == 'verified':
            # Edge case: verified but group not granted (membership cancelled
            # or pre-city_club user). Let the standard flow handle it.
            return super()._login_redirect(uid, redirect=redirect)

        return _RESIDENCY_REDIRECT
