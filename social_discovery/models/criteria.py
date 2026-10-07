from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


# Gender / orientation / availability selections mirror club_social_profile.profile
_GENDER = [
    ('homme', 'Man'), ('femme', 'Woman'),
    ('trans_homme', 'Trans man'), ('trans_femme', 'Trans woman'),
    ('non_binaire', 'Non-binary'), ('autre', 'Other'),
]
_ORIENTATION = [
    ('hetero', 'Straight'), ('gay', 'Gay / Lesbian'),
    ('bi', 'Bisexual'), ('pan', 'Pansexual'),
    ('asexuel', 'Asexual'), ('queer', 'Queer'),
    ('autre', 'Other'),
]
_AVAILABILITY = [
    ('disponible', 'Available / Looking'),
    ('couple_ouvert', 'Open relationship'),
    ('couple_ferme', 'Closed relationship'),
]


class DiscoveryCriteria(models.Model):
    _name = 'social_discovery.criteria'
    _description = 'Discovery Search Criteria'
    _order = 'name asc'

    profile_id = fields.Many2one(
        'club_social_profile.profile', required=True,
        ondelete='cascade', index=True,
    )
    name = fields.Char('Search Name', required=True, default=lambda s: _('My Search'))
    is_default = fields.Boolean(
        'Default Search',
        help='Loaded automatically when opening Discovery.',
    )

    # ── Age ───────────────────────────────────────────────────────────────────
    min_age = fields.Integer('Min Age', default=18)
    max_age = fields.Integer('Max Age', default=0,
                             help='0 = no upper limit')

    # ── Location ──────────────────────────────────────────────────────────────
    city = fields.Char('City', help='Partial, case-insensitive match')

    # ── Identity filters ──────────────────────────────────────────────────────
    gender_ids = fields.Many2many(
        'social_discovery.gender_value',
        'social_discovery_criteria_gender_rel', 'criteria_id', 'value_id',
        string='Gender (any if empty)',
    )
    orientation_ids = fields.Many2many(
        'social_discovery.orientation_value',
        'social_discovery_criteria_orientation_rel', 'criteria_id', 'value_id',
        string='Orientation (any if empty)',
    )
    availability_ids = fields.Many2many(
        'social_discovery.availability_value',
        'social_discovery_criteria_availability_rel', 'criteria_id', 'value_id',
        string='Availability (any if empty)',
    )

    # ── Profile content ───────────────────────────────────────────────────────
    looking_for_ids = fields.Many2many(
        'club_social_profile.looking_for',
        'social_discovery_criteria_looking_for_rel', 'criteria_id', 'lf_id',
        string='Looking For (overlap match)',
    )
    language_ids = fields.Many2many(
        'club_social_profile.language',
        'social_discovery_criteria_language_rel', 'criteria_id', 'lang_id',
        string='Speaks (overlap match)',
    )

    # ── Quality ───────────────────────────────────────────────────────────────
    has_photo = fields.Boolean('Has Profile Photo')
    age_verified = fields.Boolean('Age Verified (18+)')
    onboarding_done = fields.Boolean('Onboarding Completed')

    # ── Consent / visibility ──────────────────────────────────────────────────
    reachable_only = fields.Boolean(
        'Reachable Only',
        help='Exclude profiles with an active consent gate I have not yet passed.',
    )
    in_circles_only = fields.Boolean(
        'In My Circles Only',
        help='Only show profiles that have added me to at least one of their circles.',
    )

    # ── Results ───────────────────────────────────────────────────────────────
    result_count = fields.Integer(compute='_compute_result_count', string='Results')

    @api.depends(
        'min_age', 'max_age', 'city', 'gender_ids', 'orientation_ids',
        'availability_ids', 'looking_for_ids', 'language_ids',
        'has_photo', 'age_verified', 'onboarding_done',
        'reachable_only', 'in_circles_only',
    )
    def _compute_result_count(self):
        for crit in self:
            crit.result_count = len(crit._find_profiles())

    # ── Constraint ────────────────────────────────────────────────────────────

    @api.constrains('min_age', 'max_age')
    def _check_age_range(self):
        for crit in self:
            if crit.min_age < 18:
                raise ValidationError(_('Minimum age must be 18 or higher.'))
            if crit.max_age and crit.max_age < crit.min_age:
                raise ValidationError(_('Maximum age must be greater than minimum age.'))

    @api.constrains('is_default', 'profile_id')
    def _check_single_default(self):
        for crit in self:
            if crit.is_default and self.search_count([
                ('profile_id', '=', crit.profile_id.id),
                ('is_default', '=', True),
                ('id', '!=', crit.id),
            ]):
                raise ValidationError(_('Only one search can be the default.'))

    # ── Core search logic ─────────────────────────────────────────────────────

    def _find_profiles(self):
        """Return matching Club Social Profile records, respecting visibility rules."""
        self.ensure_one()
        from datetime import date
        current_year = date.today().year

        searcher_profile = self.profile_id
        searcher_user = searcher_profile.user_id

        domain = [
            ('user_id', '!=', searcher_user.id),
            # Only discover profiles that are visible to all members
            ('visibility', '=', 'members'),
        ]

        # Age filters: convert to birth_year (computed 'age' field is not stored)
        # age >= min_age  →  birth_year <= current_year - min_age
        # age <= max_age  →  birth_year >= current_year - max_age
        if self.min_age and self.min_age > 18:
            domain += [
                ('birth_year', '!=', 0),
                ('birth_year', '<=', current_year - self.min_age),
            ]
        if self.max_age:
            domain += [
                ('birth_year', '!=', 0),
                ('birth_year', '>=', current_year - self.max_age),
            ]
        if self.city:
            domain.append(('city', 'ilike', self.city))
        if self.has_photo:
            domain.append(('profile_image', '!=', False))
        if self.age_verified:
            domain.append(('age_verified', '=', True))
        if self.onboarding_done:
            domain.append(('onboarding_done', '=', True))

        if self.gender_ids:
            domain.append(('gender', 'in', self.gender_ids.mapped('value')))
        if self.orientation_ids:
            domain.append(('orientation', 'in', self.orientation_ids.mapped('value')))
        if self.availability_ids:
            domain.append(('availability', 'in', self.availability_ids.mapped('value')))

        if self.looking_for_ids:
            domain.append(('looking_for_ids', 'in', self.looking_for_ids.ids))
        if self.language_ids:
            domain.append(('language_ids', 'in', self.language_ids.ids))

        profiles = self.env['club_social_profile.profile'].search(domain)

        # Python-level post-filters (require join logic or cross-model checks)
        if self.in_circles_only:
            profiles = profiles.filtered(
                lambda p: p.is_in_any_circle(searcher_user)
            )

        if self.reachable_only and 'social_consent.gate' in self.env:
            profiles = profiles.filtered(
                lambda p: self._is_reachable(p, searcher_user)
            )

        return profiles

    def _is_reachable(self, target_profile, searcher_user):
        """True if target has no active gate, or searcher's request is approved."""
        if 'social_consent.gate' not in self.env:
            return True
        gate = self.env['social_consent.gate'].search([
            ('profile_id', '=', target_profile.id),
            ('is_active', '=', True),
        ], limit=1)
        if not gate:
            return True
        approved = self.env['social_consent.request'].search_count([
            ('gate_id', '=', gate.id),
            ('requester_id', '=', searcher_user.id),
            ('state', '=', 'approved'),
        ])
        return bool(approved)

    def action_search(self):
        """Open the list of matching profiles."""
        self.ensure_one()
        profiles = self._find_profiles()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Discovery: %(name)s', name=self.name),
            'res_model': 'club_social_profile.profile',
            'view_mode': 'list,form',
            'views': [(False, 'list'), (False, 'form')],  # requis par Odoo 20
            'domain': [('id', 'in', profiles.ids)],
            'context': {'search_default_': 0},
        }


# ── Simple codelist models for multi-select filters ───────────────────────────

class GenderValue(models.Model):
    _name = 'social_discovery.gender_value'
    _description = 'Discovery: Gender Filter Value'
    _order = 'sequence asc'

    name = fields.Char(required=True, translate=True)
    value = fields.Char(required=True)
    sequence = fields.Integer(default=10)


class OrientationValue(models.Model):
    _name = 'social_discovery.orientation_value'
    _description = 'Discovery: Orientation Filter Value'
    _order = 'sequence asc'

    name = fields.Char(required=True, translate=True)
    value = fields.Char(required=True)
    sequence = fields.Integer(default=10)


class AvailabilityValue(models.Model):
    _name = 'social_discovery.availability_value'
    _description = 'Discovery: Availability Filter Value'
    _order = 'sequence asc'

    name = fields.Char(required=True, translate=True)
    value = fields.Char(required=True)
    sequence = fields.Integer(default=10)
