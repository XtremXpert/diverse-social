import base64
import datetime

from odoo import _
from odoo.http import request, route
from odoo.addons.portal.controllers.portal import CustomerPortal

_STEPS = ['welcome', 'about', 'preferences', 'done']


def _step_titles():
    return {
        'welcome': _('Welcome'),
        'about': _('About me'),
        'preferences': _('My preferences'),
        'done': _('Profile complete!'),
    }


class OnboardingPortal(CustomerPortal):

    def home(self, **kw):
        """Redirect newly active members to /onboarding (once per session)."""
        if not request.session.get('onboarding_prompted'):
            user = request.env.user
            partner = user.partner_id.sudo()
            if getattr(partner, 'member_state', None) == 'active':
                profile = request.env['club_social_profile.profile'].sudo().search(
                    [('user_id', '=', user.id)], limit=1
                )
                if profile and not profile.onboarding_done:
                    request.session['onboarding_prompted'] = True
                    return request.redirect('/onboarding')
        return super().home(**kw)

    @route('/onboarding', auth='user', website=True, sitemap=False)
    def onboarding(self, step=None, **kw):
        profile = request.env['club_social_profile.profile'].sudo().get_or_create_for_user(
            request.env.user
        )
        if step not in _STEPS:
            step = 'done' if profile.onboarding_done else 'welcome'
        return self._render_onboarding(profile, step)

    # ── Step 1: profile picture ───────────────────────────────────────────────

    @route('/onboarding/save/welcome', auth='user', methods=['POST'], website=True, csrf=True)
    def save_welcome(self, profile_image=None, **kw):
        profile = request.env['club_social_profile.profile'].sudo().get_or_create_for_user(
            request.env.user
        )
        vals = {}
        if profile_image and getattr(profile_image, 'filename', None):
            vals['profile_image'] = base64.b64encode(profile_image.read()).decode('ascii')
        if vals:
            profile.write(vals)
        # Stay on `welcome` so the user can immediately see their newly
        # uploaded photo before clicking "Next". Moving to the next step is
        # now a separate link, not the submit button of the upload form.
        return request.redirect('/onboarding?step=welcome')

    # ── Step 2: about ─────────────────────────────────────────────────────────

    @route('/onboarding/save/about', auth='user', methods=['POST'], website=True, csrf=True)
    def save_about(self, pronouns='', bio='', birth_year='', city='', region='',
                   gender='non_specifie', orientation='non_specifie', quote='', **kw):
        profile = request.env['club_social_profile.profile'].sudo().get_or_create_for_user(
            request.env.user
        )
        try:
            birth_year_int = int(birth_year) if birth_year.strip() else 0
        except (ValueError, AttributeError):
            birth_year_int = 0

        if birth_year_int:
            age = datetime.date.today().year - birth_year_int
            if 0 < age < 18:
                return self._render_onboarding(
                    profile, 'about',
                    error=_("You must be 18 or older to access the social network."),
                    form_values={'pronouns': pronouns, 'bio': bio,
                                 'birth_year': birth_year, 'city': city,
                                 'region': region, 'gender': gender,
                                 'orientation': orientation, 'quote': quote},
                )

        _valid_gender = {'homme', 'femme', 'trans_homme', 'trans_femme',
                         'non_binaire', 'autre', 'non_specifie'}
        _valid_orient = {'hetero', 'gay', 'bi', 'pan', 'asexuel',
                         'queer', 'autre', 'non_specifie'}

        profile.write({
            'pronouns': pronouns.strip() or False,
            'bio': bio.strip() or False,
            'birth_year': birth_year_int,
            'city': city.strip() or False,
            'region': region.strip() or False,
            'gender': gender if gender in _valid_gender else 'non_specifie',
            'orientation': orientation if orientation in _valid_orient else 'non_specifie',
            'quote': quote.strip()[:200] or False,
        })
        return request.redirect('/onboarding?step=preferences')

    # ── Step 3: preferences ───────────────────────────────────────────────────

    @route('/onboarding/save/preferences', auth='user', methods=['POST'], website=True, csrf=True)
    def save_preferences(self, visibility='members', availability='non_specifie',
                         digest_email_enabled=False, **kw):
        profile = request.env['club_social_profile.profile'].sudo().get_or_create_for_user(
            request.env.user
        )
        valid_visibilities = ('members', 'connections')
        valid_availabilities = ('disponible', 'couple_ouvert', 'couple_ferme',
                                'pas_disponible', 'non_specifie')

        # Many2many: looking_for_ids and language_ids via getlist
        form = request.httprequest.form
        looking_for_raw = [int(x) for x in form.getlist('looking_for_ids') if x.isdigit()]
        language_raw    = [int(x) for x in form.getlist('language_ids') if x.isdigit()]

        # Make sure submitted IDs exist
        valid_lf  = request.env['club_social_profile.looking_for'].sudo().browse(looking_for_raw).exists().ids
        valid_lng = request.env['club_social_profile.language'].sudo().browse(language_raw).exists().ids

        profile.write({
            'visibility': visibility if visibility in valid_visibilities else 'members',
            'availability': availability if availability in valid_availabilities else 'non_specifie',
            'digest_email_enabled': bool(digest_email_enabled),
            'looking_for_ids': [(6, 0, valid_lf)],
            'language_ids':    [(6, 0, valid_lng)],
        })
        profile.write({'onboarding_done': True})
        return request.redirect('/onboarding?step=done')

    # ── Skip ──────────────────────────────────────────────────────────────────

    @route('/onboarding/skip', auth='user', methods=['POST'], website=True, csrf=True)
    def skip(self, **kw):
        return request.redirect('/web')

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _render_onboarding(self, profile, step, error=None, form_values=None):
        looking_for_opts = request.env['club_social_profile.looking_for'].sudo().search(
            [], order='sequence asc'
        )
        language_opts = request.env['club_social_profile.language'].sudo().search(
            [], order='sequence asc'
        )
        # `no-store` disables the browser bfcache: without it, clicking
        # "Back" after a photo upload would re-serve the cached HTML with
        # the old `?unique=...` and the image would never refresh.
        return request.render('social_onboarding.portal_onboarding', {
            'profile': profile,
            'step': step,
            'step_titles': _step_titles(),
            'steps': _STEPS,
            'step_index': _STEPS.index(step),
            'error': error,
            'form_values': form_values or {},
            'looking_for_opts': looking_for_opts,
            'language_opts': language_opts,
            'page_name': 'onboarding',
        }, headers={'Cache-Control': 'no-store, max-age=0'})
