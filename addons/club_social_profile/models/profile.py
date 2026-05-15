from datetime import date

from odoo import fields, models, api, _
from odoo.exceptions import ValidationError


class ClubSocialProfile(models.Model):
    _name = 'club_social_profile.profile'
    _description = 'Member Social Profile'
    _rec_name = 'login'

    user_id = fields.Many2one('res.users', required=True, ondelete='cascade', index=True)
    partner_id = fields.Many2one(related='user_id.partner_id', store=True)
    login = fields.Char(related='user_id.login', store=True, readonly=True)

    # ── Photos ────────────────────────────────────────────────────────────────
    profile_image = fields.Image(max_width=400, max_height=400)
    cover_image = fields.Image(max_width=1200, max_height=400)

    # ── Identity ──────────────────────────────────────────────────────────────
    pronouns = fields.Char()
    birth_year = fields.Integer()
    age = fields.Integer(compute='_compute_age')

    @api.depends('birth_year')
    def _compute_age(self):
        current_year = date.today().year
        for p in self:
            p.age = (current_year - p.birth_year) if p.birth_year and 1900 < p.birth_year < current_year else 0

    gender = fields.Selection([
        ('homme', 'Man'), ('femme', 'Woman'),
        ('trans_homme', 'Trans man'), ('trans_femme', 'Trans woman'),
        ('non_binaire', 'Non-binary'), ('autre', 'Other'),
        ('non_specifie', 'Prefer not to say'),
    ])
    orientation = fields.Selection([
        ('hetero', 'Straight'), ('gay', 'Gay / Lesbian'),
        ('bi', 'Bisexual'), ('pan', 'Pansexual'),
        ('asexuel', 'Asexual'), ('queer', 'Queer'),
        ('autre', 'Other'), ('non_specifie', 'Prefer not to say'),
    ])

    # ── Bio ───────────────────────────────────────────────────────────────────
    bio = fields.Text()
    quote = fields.Char(size=200)

    # ── Availability ──────────────────────────────────────────────────────────
    availability = fields.Selection([
        ('disponible', 'Available / Looking'),
        ('couple_ouvert', 'Open relationship'),
        ('couple_ferme', 'Closed relationship'),
        ('pas_disponible', 'Not available'),
        ('non_specifie', 'Not specified'),
    ], default='non_specifie')

    # ── Languages & Looking For ───────────────────────────────────────────────
    language_ids = fields.Many2many('club_social_profile.language', string='Spoken Languages')
    looking_for_ids = fields.Many2many('club_social_profile.looking_for', string='Looking For')

    # ── Location ──────────────────────────────────────────────────────────────
    city = fields.Char()
    region = fields.Char(string='Region / Province')

    # ── Onboarding ───────────────────────────────────────────────────────────
    onboarding_done = fields.Boolean(default=False, index=True)

    # ── Visibility & Privacy ─────────────────────────────────────────────────
    stealth_name = fields.Char(
        string='Pseudonym (stealth)',
        help='Alternative name shown to connections instead of login.',
    )
    visibility = fields.Selection([
        ('members', 'Club Members'),
        ('connections', 'Connections Only'),
    ], default='members', required=True)
    allow_link_sharing = fields.Boolean(default=True, string='Allow profile link sharing')
    digest_email_enabled = fields.Boolean(default=True, string='Weekly digest email')

    # ── Stats ─────────────────────────────────────────────────────────────────
    profile_view_count = fields.Integer(default=0, readonly=True)
    profile_visit_ids = fields.One2many('club_social_profile.profile_visit', 'profile_id', string='Visits')

    # ── Age verification ─────────────────────────────────────────────────────
    age_verified = fields.Boolean(compute='_compute_age_verified', string='Age Verified (18+)', store=True)

    @api.depends('birth_year')
    def _compute_age_verified(self):
        for p in self:
            p.age_verified = p.age >= 18

    @api.constrains('birth_year')
    def _check_birth_year_adult(self):
        for p in self:
            if p.birth_year and 0 < p.age < 18:
                raise ValidationError(_('You must be 18 years or older to register.'))

    @api.constrains('user_id')
    def _check_unique_user(self):
        for p in self:
            if self.search_count([('user_id', '=', p.user_id.id), ('id', '!=', p.id)]):
                raise ValidationError(_('A profile already exists for this user.'))

    @api.model
    def get_or_create_for_user(self, user):
        profile = self.search([('user_id', '=', user.id)], limit=1)
        if not profile:
            profile = self.create({'user_id': user.id})
        return profile
