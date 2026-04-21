from . import controllers
from . import models


def _post_init_hook(env):
    """Activer la restriction d'accès événements sur tous les sites existants."""
    env['website'].search([]).write({'event_login_required': True})
