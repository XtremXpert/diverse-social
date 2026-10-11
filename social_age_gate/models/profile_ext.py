from odoo import fields, models


class ClubSocialProfile(models.Model):
    _inherit = 'club_social_profile.profile'

    age_gate_passed = fields.Boolean(
        'Age verification (18+) passed', default=False, index=True,
        help="Set to True only when the member explicitly confirms their age "
             "via the portal (/age-verify) or the onboarding wizard. "
             "Never set automatically from birth_year — that would bypass "
             "the explicit consent step.",
    )
