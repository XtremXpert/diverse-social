import datetime

from odoo import _, api, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import BinaryBytes

# Champs que l'application lit et modifie, comme les trois étapes de /onboarding sur le site.
TEXT_FIELDS = {'pronouns': 64, 'bio': 2000, 'city': 128, 'region': 128, 'quote': 200}
SELECTION_FIELDS = ('gender', 'orientation', 'availability', 'visibility')
OPTION_MODELS = {'looking_for_ids': 'club_social_profile.looking_for', 'language_ids': 'club_social_profile.language'}
ADULT_AGE = 18


class ClubSocialProfileMobile(models.Model):
    _inherit = 'club_social_profile.profile'

    # ── Lecture ──────────────────────────────────────────────────────────────

    def _mobile_payload(self):
        """Profil du membre et choix possibles, libellés dans sa langue."""
        self.ensure_one()
        profile = self.with_context(lang=self.user_id.lang)
        values = {name: profile[name] or None for name in TEXT_FIELDS}
        values.update({name: profile[name] or None for name in SELECTION_FIELDS})
        values.update({
            'birth_year': profile.birth_year or None,
            'digest_email_enabled': profile.digest_email_enabled,
            'looking_for_ids': profile.looking_for_ids.ids,
            'language_ids': profile.language_ids.ids,
            'has_photo': bool(profile.profile_image),
        })
        described = profile.fields_get(list(SELECTION_FIELDS), ['selection'])
        options = {name: [{'value': v, 'label': label} for v, label in described[name]['selection']]
                   for name in SELECTION_FIELDS}
        for name, model in OPTION_MODELS.items():
            records = profile.env[model].sudo().with_context(lang=self.user_id.lang).search([])
            options[name] = [{'id': r.id, 'name': r.name} for r in records]
        return {'profile': values, 'options': options, 'onboarding_done': profile.onboarding_done,
                'adult_age': ADULT_AGE}

    # ── Modification ─────────────────────────────────────────────────────────

    @api.model
    def _mobile_birth_year(self, value):
        """Année de naissance valide d'un adulte, sinon ``UserError`` (0 efface)."""
        if value in (None, '', 0):
            return 0
        try:
            year = int(value)
        except (TypeError, ValueError):
            raise UserError(_("Année de naissance invalide.")) from None
        this_year = datetime.date.today().year
        if not 1900 < year <= this_year:
            raise UserError(_("Année de naissance invalide."))
        if this_year - year < ADULT_AGE:
            raise UserError(_("Le club est réservé aux personnes de %s ans ou plus.", ADULT_AGE))
        return year

    def _mobile_update(self, data):
        """Écrit les champs reçus (les autres restent tels quels). ``onboarding_done`` n'en fait pas partie."""
        self.ensure_one()
        vals = {}
        for name, size in TEXT_FIELDS.items():
            if name in data:
                text = data[name]
                if text is not None and not isinstance(text, str):
                    raise UserError(_("Champ « %s » : texte attendu.", name))
                vals[name] = (text or '').strip()[:size] or False
        allowed = {name: {v for v, _label in self._fields[name].selection} for name in SELECTION_FIELDS}
        for name in SELECTION_FIELDS:
            if name in data:
                if data[name] not in allowed[name]:
                    raise UserError(_("Champ « %s » : valeur inconnue.", name))
                vals[name] = data[name]
        if 'birth_year' in data:
            vals['birth_year'] = self._mobile_birth_year(data['birth_year'])
        if 'digest_email_enabled' in data:
            vals['digest_email_enabled'] = bool(data['digest_email_enabled'])
        for name, model in OPTION_MODELS.items():
            if name in data:
                ids = data[name]
                if not isinstance(ids, list) or not all(isinstance(i, int) for i in ids):
                    raise UserError(_("Champ « %s » : liste d'identifiants attendue.", name))
                vals[name] = [(6, 0, self.env[model].sudo().browse(ids).exists().ids)]
        if vals:
            self.sudo().write(vals)

    def _mobile_set_photo(self, data):
        """Photo de profil (octets d'une image) ; Odoo la réduit à 400 × 400."""
        self.ensure_one()
        try:
            self.sudo().write({'profile_image': BinaryBytes(data)})
            self.flush_recordset(['profile_image'])
        except (UserError, ValidationError, ValueError) as e:
            raise UserError(_("Image illisible.")) from e

    def _mobile_complete(self):
        """Fin de l'accueil dans l'application : exige l'année de naissance d'un adulte."""
        self.ensure_one()
        if not self.birth_year:
            raise UserError(_("L'année de naissance est obligatoire."))
        self._mobile_birth_year(self.birth_year)
        self.sudo().write({'onboarding_done': True})
