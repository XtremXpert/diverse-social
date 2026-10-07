import base64
import datetime

from odoo import _
from odoo.addons.portal.controllers.portal import CustomerPortal
from odoo.http import request, route

_VALID_GENDER = frozenset({
    'homme', 'femme', 'trans_homme', 'trans_femme', 'non_binaire', 'autre', 'non_specifie',
})
_VALID_ORIENT = frozenset({
    'hetero', 'gay', 'bi', 'pan', 'asexuel', 'queer', 'autre', 'non_specifie',
})
_VALID_AVAIL = frozenset({
    'disponible', 'couple_ouvert', 'couple_ferme', 'pas_disponible', 'non_specifie',
})
_VALID_VIS = frozenset({'members', 'connections'})


class ProfileEditPortal(CustomerPortal):

    def _get_own_profile(self):
        return request.env['club_social_profile.profile'].sudo().get_or_create_for_user(
            request.env.user
        )

    def _edit_context(self, profile, error=None, success=None, section='identity'):
        looking_for_opts = request.env['club_social_profile.looking_for'].sudo().search(
            [], order='sequence asc'
        )
        language_opts = request.env['club_social_profile.language'].sudo().search(
            [], order='sequence asc'
        )
        return {
            'profile': profile,
            'error': error,
            'success': success,
            'section': section,
            'looking_for_opts': looking_for_opts,
            'language_opts': language_opts,
            'ui_langs': request.env['res.lang'].sudo().search([]),
            'page_name': 'profile_edit',
        }

    # ── Affichage ─────────────────────────────────────────────────────────────

    @route('/my/profile/edit', auth='user', website=True, sitemap=False)
    def edit(self, section='identity', saved='', **kw):
        profile = self._get_own_profile()
        # saved=1 : retour de redirection post-sauvegarde (ex. changement de
        # langue d'interface → l'URL localisée change, on garde le feedback).
        success = _("Preferences saved.") if saved else None
        return request.render(
            'club_social_profile.portal_profile_edit',
            self._edit_context(profile, section=section, success=success),
        )

    # ── Identity ──────────────────────────────────────────────────────────────

    @route('/my/profile/edit/identity', auth='user', methods=['GET', 'POST'], website=True, csrf=True)
    def save_identity(self, pronouns='', bio='', birth_year='', city='', region='',
                      gender='non_specifie', orientation='non_specifie', quote='',
                      profile_image=None, cover_image=None, **kw):
        if request.httprequest.method == 'GET':
            return request.redirect('/my/profile/edit')
        profile = self._get_own_profile()

        try:
            birth_year_int = int(birth_year) if str(birth_year).strip() else 0
        except (ValueError, TypeError):
            birth_year_int = 0

        if birth_year_int:
            age = datetime.date.today().year - birth_year_int
            if 0 < age < 18:
                return request.render(
                    'club_social_profile.portal_profile_edit',
                    self._edit_context(
                        profile, section='identity',
                        error=_("You must be 18 or older."),
                    ),
                )

        vals = {
            'pronouns': pronouns.strip() or False,
            'bio': bio.strip() or False,
            'birth_year': birth_year_int,
            'city': city.strip() or False,
            'region': region.strip() or False,
            'gender': gender if gender in _VALID_GENDER else 'non_specifie',
            'orientation': orientation if orientation in _VALID_ORIENT else 'non_specifie',
            'quote': (quote.strip() or '')[:200] or False,
        }
        if profile_image and getattr(profile_image, 'filename', None):
            vals['profile_image'] = base64.b64encode(profile_image.read()).decode('ascii')
        if cover_image and getattr(cover_image, 'filename', None):
            vals['cover_image'] = base64.b64encode(cover_image.read()).decode('ascii')

        profile.write(vals)
        return request.render(
            'club_social_profile.portal_profile_edit',
            self._edit_context(profile, section='identity', success=_("Profile updated.")),
        )

    # ── Preferences ───────────────────────────────────────────────────────────

    @route('/my/profile/edit/preferences', auth='user', methods=['GET', 'POST'], website=True, csrf=True)
    def save_profile_preferences(self, visibility='members', availability='non_specifie',
                                 digest_email_enabled=False, stealth_name='', ui_lang='', **kw):
        if request.httprequest.method == 'GET':
            return request.redirect('/my/profile/edit?section=preferences')
        profile = self._get_own_profile()
        form = request.httprequest.form
        looking_for_raw = [int(x) for x in form.getlist('looking_for_ids') if x.isdigit()]
        language_raw    = [int(x) for x in form.getlist('language_ids') if x.isdigit()]

        valid_lf  = request.env['club_social_profile.looking_for'].sudo().browse(looking_for_raw).exists().ids
        valid_lng = request.env['club_social_profile.language'].sudo().browse(language_raw).exists().ids

        profile.write({
            'visibility':           visibility if visibility in _VALID_VIS else 'members',
            'availability':         availability if availability in _VALID_AVAIL else 'non_specifie',
            'digest_email_enabled': bool(digest_email_enabled),
            'stealth_name':         stealth_name.strip()[:80] or False,
            'looking_for_ids':      [(6, 0, valid_lf)],
            'language_ids':         [(6, 0, valid_lng)],
        })

        # Langue de l'interface et des courriels (res.users.lang — champ
        # auto-modifiable par l'usager, cf. SELF_WRITEABLE_FIELDS). Le
        # sélecteur fr/en du site ne change que le cookie de session ; ici on
        # change la langue de PROFIL : courriels (digest, notifications) et
        # langue par défaut à la connexion.
        user = request.env.user
        if ui_lang and ui_lang != user.lang:
            lang = request.env['res.lang'].sudo().search([('code', '=', ui_lang)], limit=1)
            if lang:
                user.write({'lang': lang.code})
                # Redirige vers l'URL localisée pour que l'interface bascule
                # immédiatement (le rendu suit l'URL, pas user.lang).
                default = request.env.website.default_lang_id
                prefix = '' if lang == default else '/' + lang.url_code
                resp = request.redirect(
                    '%s/my/profile/edit?section=preferences&saved=1' % prefix)
                resp.set_cookie('frontend_lang', lang.code)
                return resp

        return request.render(
            'club_social_profile.portal_profile_edit',
            self._edit_context(profile, section='preferences', success=_("Preferences saved.")),
        )
