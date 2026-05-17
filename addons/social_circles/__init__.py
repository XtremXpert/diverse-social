from . import models
from . import controllers


def post_init_hook(env):
    """Provision the default 'Connaissances' circle for all existing profiles
    that do not already have one. Runs once at module installation."""
    from .models.profile_ext import DEFAULT_CIRCLE_NAME, DEFAULT_CIRCLE_SEQUENCE
    Profile = env['club_social_profile.profile'].sudo()
    Circle = env['social_circles.circle'].sudo()
    for profile in Profile.search([]):
        already = Circle.search_count([
            ('profile_id', '=', profile.id),
            ('name', '=', DEFAULT_CIRCLE_NAME),
        ])
        if not already:
            Circle.create({
                'profile_id': profile.id,
                'name': DEFAULT_CIRCLE_NAME,
                'sequence': DEFAULT_CIRCLE_SEQUENCE,
            })
