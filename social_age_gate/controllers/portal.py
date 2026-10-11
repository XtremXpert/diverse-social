from odoo import _, fields
from odoo.http import request, route
from odoo.addons.social_onboarding.controllers.portal import OnboardingPortal


def _get_profile(user):
    return request.env['club_social_profile.profile'].sudo().search(
        [('user_id', '=', user.id)], limit=1,
    )


class AgeGatePortal(OnboardingPortal):

    # Redécore explicitement les overrides de OnboardingPortal / CustomerPortal
    # pour éviter les warnings "endpoint not decorated by @route()" au boot.
    @route(['/my', '/my/home'], type='http', auth='user', website=True)
    def home(self, **kw):
        profile = _get_profile(request.env.user)
        if profile and not profile.age_gate_passed:
            return request.redirect('/age-verify')
        return super().home(**kw)

    @route('/onboarding/skip', auth='user', methods=['POST'], website=True, csrf=True)
    def skip(self, **kw):
        profile = _get_profile(request.env.user)
        if profile and not profile.age_gate_passed:
            return request.redirect('/age-verify')
        return super().skip(**kw)

    @route('/age-verify', auth='user', sitemap=False)
    def age_verify(self, error=None, birth_year=None, **kw):
        profile = _get_profile(request.env.user)
        if not profile:
            return request.redirect('/web')
        if profile.age_gate_passed:
            return request.redirect('/web')
        return request.render('social_age_gate.portal_age_gate', {
            'profile': profile,
            'error': error,
            'birth_year': birth_year,
            'max_birth_year': fields.Date.today().year - 18,
            'page_name': 'age_gate',
        })

    @route('/age-verify/submit', auth='user', methods=['POST'], csrf=True, sitemap=False)
    def age_verify_submit(self, birth_year='', confirmed=None, **kw):
        profile = _get_profile(request.env.user)
        if not profile:
            return request.redirect('/web')
        if profile.age_gate_passed:
            return request.redirect('/web')

        error = None
        birth_year_int = 0
        try:
            birth_year_int = int(birth_year.strip()) if birth_year and birth_year.strip() else 0
        except (ValueError, AttributeError):
            birth_year_int = 0

        if not confirmed:
            error = _("You must check the box to confirm your age.")
        elif birth_year_int:
            age = fields.Date.today().year - birth_year_int
            if birth_year_int < 1900:
                error = _("Please enter a valid birth year.")
            elif age < 18:
                error = _("You must be 18 or older to access this network.")

        if error:
            return request.render('social_age_gate.portal_age_gate', {
                'profile': profile,
                'error': error,
                'birth_year': birth_year,
                'max_birth_year': fields.Date.today().year - 18,
                'page_name': 'age_gate',
            })

        vals = {'age_gate_passed': True}
        if birth_year_int:
            vals['birth_year'] = birth_year_int
        profile.sudo().write(vals)

        if not profile.onboarding_done:
            return request.redirect('/onboarding')
        return request.redirect('/web')
