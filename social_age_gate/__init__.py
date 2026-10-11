from . import models, controllers


def post_init_hook(env):
    from odoo import fields
    Profile = env['club_social_profile.profile']
    today_year = fields.Date.today().year
    profiles_to_migrate = Profile.sudo().search([
        ('birth_year', '>', 0),
        ('birth_year', '<=', today_year - 18),
        ('age_gate_passed', '=', False),
    ])
    if profiles_to_migrate:
        profiles_to_migrate.write({'age_gate_passed': True})
