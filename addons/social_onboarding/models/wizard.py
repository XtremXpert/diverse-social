from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


_STEPS = ['welcome', 'about', 'preferences', 'done']


class SocialOnboardingWizard(models.TransientModel):
    _name = 'social_onboarding.wizard'
    _description = "Assistant d'intégration réseau social"

    step = fields.Selection([
        ('welcome', 'Bienvenue'),
        ('about', 'À propos'),
        ('preferences', 'Préférences'),
        ('done', 'Terminé'),
    ], default='welcome', required=True)

    profile_id = fields.Many2one('club_social_profile.profile', readonly=True)

    # ── Étape 1 : photo ───────────────────────────────────────────────────────
    profile_image = fields.Image(max_width=400, max_height=400, string='Photo de profil')

    # ── Étape 2 : à propos ────────────────────────────────────────────────────
    pronouns = fields.Char('Pronoms')
    bio = fields.Text('Bio')
    birth_year = fields.Integer("Année de naissance")
    city = fields.Char('Ville')

    # ── Étape 3 : préférences ─────────────────────────────────────────────────
    visibility = fields.Selection([
        ('members', 'Membres du club'),
        ('connections', 'Connexions uniquement'),
    ], string='Visibilité du profil', default='members', required=True)
    availability = fields.Selection([
        ('disponible', 'Disponible / En recherche'),
        ('couple_ouvert', 'Couple ouvert'),
        ('couple_ferme', 'Couple fermé'),
        ('pas_disponible', 'Pas disponible'),
        ('non_specifie', 'Non spécifié'),
    ], string='Disponibilité', default='non_specifie')
    digest_email_enabled = fields.Boolean(
        'Recevoir le résumé hebdomadaire par courriel', default=True,
    )

    # ── Ouverture ─────────────────────────────────────────────────────────────

    @api.model
    def action_open(self):
        """Crée ou charge l'assistant pour l'utilisateur courant."""
        Profile = self.env['club_social_profile.profile']
        profile = Profile.sudo().get_or_create_for_user(self.env.user)
        wizard = self.create({
            'profile_id': profile.id,
            'profile_image': profile.profile_image,
            'pronouns': profile.pronouns or False,
            'bio': profile.bio or False,
            'birth_year': profile.birth_year or 0,
            'city': profile.city or False,
            'visibility': profile.visibility or 'members',
            'availability': profile.availability or 'non_specifie',
            'digest_email_enabled': profile.digest_email_enabled,
            'step': 'welcome' if not profile.onboarding_done else 'done',
        })
        return wizard._build_action()

    def _build_action(self):
        return {
            'type': 'ir.actions.act_window',
            'name': _("Compléter mon profil"),
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'current',
        }

    # ── Navigation ────────────────────────────────────────────────────────────

    def action_next(self):
        self.ensure_one()
        self._validate_current_step()
        self._save_to_profile()
        idx = _STEPS.index(self.step)
        if idx < len(_STEPS) - 1:
            self.step = _STEPS[idx + 1]
        return self._build_action()

    def action_previous(self):
        self.ensure_one()
        idx = _STEPS.index(self.step)
        if idx > 0:
            self.step = _STEPS[idx - 1]
        return self._build_action()

    def action_finish(self):
        self.ensure_one()
        self._save_to_profile()
        self.profile_id.sudo().write({'onboarding_done': True})
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _("Bienvenue !"),
                'message': _("Votre profil est maintenant complet. Bonne exploration !"),
                'type': 'success',
                'sticky': False,
                'next': {
                    'type': 'ir.actions.act_window',
                    'res_model': 'social_base.post',
                    'view_mode': 'list,form',
                    'target': 'current',
                },
            },
        }

    def action_skip(self):
        """Ferme l'assistant sans marquer le profil comme complété."""
        self.ensure_one()
        self._save_to_profile()
        return {'type': 'ir.actions.act_window_close'}

    # ── Sauvegarde & validation ───────────────────────────────────────────────

    def _validate_current_step(self):
        """Valide les champs de l'étape courante avant de passer à la suivante."""
        if self.step == 'about' and self.birth_year:
            import datetime
            current_year = datetime.date.today().year
            age = current_year - self.birth_year
            if 0 < age < 18:
                raise ValidationError(
                    _("Vous devez avoir 18 ans ou plus pour accéder au réseau social.")
                )

    def _save_to_profile(self):
        if not self.profile_id:
            return
        self.profile_id.sudo().write({
            'profile_image': self.profile_image,
            'pronouns': self.pronouns or False,
            'bio': self.bio or False,
            'birth_year': self.birth_year or 0,
            'city': self.city or False,
            'visibility': self.visibility,
            'availability': self.availability,
            'digest_email_enabled': self.digest_email_enabled,
        })
