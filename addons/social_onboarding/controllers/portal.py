import base64
import datetime

from odoo.http import request, route
from odoo.addons.portal.controllers.portal import CustomerPortal

_STEPS = ['welcome', 'about', 'preferences', 'done']

_STEP_TITLES = {
    'welcome': 'Bienvenue',
    'about': 'À propos de moi',
    'preferences': 'Mes préférences',
    'done': 'Profil complété !',
}


class OnboardingPortal(CustomerPortal):

    def home(self, **kw):
        """Redirige les nouveaux membres actifs vers /onboarding (une fois par session)."""
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

    # ── Étape 1 : photo de profil ─────────────────────────────────────────────

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
        return request.redirect('/onboarding?step=about')

    # ── Étape 2 : à propos ────────────────────────────────────────────────────

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
                    error="Vous devez avoir 18 ans ou plus pour accéder au réseau social.",
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

    # ── Étape 3 : préférences ─────────────────────────────────────────────────

    @route('/onboarding/save/preferences', auth='user', methods=['POST'], website=True, csrf=True)
    def save_preferences(self, visibility='members', availability='non_specifie',
                         digest_email_enabled=False, **kw):
        profile = request.env['club_social_profile.profile'].sudo().get_or_create_for_user(
            request.env.user
        )
        valid_visibilities = ('members', 'connections')
        valid_availabilities = ('disponible', 'couple_ouvert', 'couple_ferme',
                                'pas_disponible', 'non_specifie')

        # Many2many : looking_for_ids et language_ids via getlist
        form = request.httprequest.form
        looking_for_raw = [int(x) for x in form.getlist('looking_for_ids') if x.isdigit()]
        language_raw    = [int(x) for x in form.getlist('language_ids') if x.isdigit()]

        # Valider que les IDs existent
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

    # ── Ignorer ───────────────────────────────────────────────────────────────

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
        return request.render('social_onboarding.portal_onboarding', {
            'profile': profile,
            'step': step,
            'step_titles': _STEP_TITLES,
            'steps': _STEPS,
            'step_index': _STEPS.index(step),
            'error': error,
            'form_values': form_values or {},
            'looking_for_opts': looking_for_opts,
            'language_opts': language_opts,
            'page_name': 'onboarding',
        })
