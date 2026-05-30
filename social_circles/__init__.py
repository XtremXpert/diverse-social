from . import models
from . import controllers


def post_init_hook(env):
    """Provision the default circle for all existing profiles that do not
    already have one. Runs once at module installation/upgrade."""
    default_type = env['social_circles.circle_type'].sudo().search(
        [('is_default', '=', True)], limit=1
    )
    if not default_type:
        return
    Profile = env['club_social_profile.profile'].sudo()
    Circle = env['social_circles.circle'].sudo()
    for profile in Profile.search([]):
        already = Circle.search_count([
            ('profile_id', '=', profile.id),
            ('type_id', '=', default_type.id),
        ])
        if not already:
            Circle.create({
                'profile_id': profile.id,
                'type_id': default_type.id,
                'sequence': default_type.sequence,
            })
