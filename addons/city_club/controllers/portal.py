from markupsafe import Markup

from odoo import _, http
from odoo.exceptions import UserError, ValidationError
from odoo.http import request


_DEFAULT_CHARTER_HTML = (
    "<p>This community has not yet published a charter. "
    "Until it does, behave like a neighbour: respect, no-spam, on-topic.</p>"
)


class CommunityHelp(http.Controller):

    @http.route('/community/help', auth='public', website=True, sitemap=True)
    def community_help(self, **kw):
        """Member-facing FAQ: how to post, how to report, community charter.

        The first two sections are app-mechanical and live in the template.
        The charter is community-specific and read from
        ``ir.config_parameter`` key ``city_club.charter_html`` so leaf
        modules customize without forking the template.

        Public auth: a prospect resident can read the charter before
        signup. No data is exposed beyond the configured text.
        """
        Param = request.env['ir.config_parameter'].sudo()
        charter_html = Param.get_param('city_club.charter_html') or _DEFAULT_CHARTER_HTML
        city_name = request.env['club_social_profile.profile'].sudo()._get_city_name()
        return request.render('city_club.community_help_page', {
            'city_name': city_name or _('this community'),
            # Wrap in Markup so QWeb renders the HTML instead of escaping it.
            'charter_html': Markup(charter_html),
        })


class ResidencyPortal(http.Controller):

    @http.route('/residency/verify', auth='user', website=True, sitemap=False,
                methods=['GET', 'POST'], csrf=True)
    def residency_verify(self, postal_code=None, notes=None, **kwargs):
        """Member-facing residency submission.

        Flow:
        - GET  → render the form, pre-filled with the current state
        - POST → submit the postal code, transition to ``pending``,
                 ping all moderators in-app.

        Accessible to any logged-in user (auth='user') — this is the
        single entry point for someone who just signed up and doesn't
        yet have ``group_social_user``.
        """
        Profile = request.env['club_social_profile.profile'].sudo()
        profile = Profile.get_or_create_for_user(request.env.user)

        error = None
        if request.httprequest.method == 'POST':
            # Savepoint required: action_submit_residency writes fields
            # before raising (postal_code, notes). Without a savepoint, the
            # partial writes survive the caught exception and the next GET
            # shows the invalid input as if it had been saved.
            try:
                with request.env.cr.savepoint():
                    profile.action_submit_residency(
                        postal_code=postal_code or '',
                        notes=notes or '',
                    )
            except (UserError, ValidationError) as e:
                # Use .args[0] to get the bare message without Odoo wrapping.
                error = e.args[0] if e.args else str(e)

        # Always reload from DB so the rendered state matches what was saved.
        profile = profile.exists()
        values = {
            'profile': profile,
            'city_name': profile._get_city_name() or _('this community'),
            'error': error,
            # Echo back submitted values on validation error so the user
            # doesn't lose their input.
            'form_postal_code': postal_code if error else profile.residency_postal_code,
            'form_notes': notes if error else profile.residency_notes,
        }
        return request.render('city_club.residency_verify_page', values)
