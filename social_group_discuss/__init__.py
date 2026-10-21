from . import models


def _post_init_hook(env):
    """Groupes déjà créés : leur conversation dès l'installation."""
    env['social_group.group'].sudo().search([])._sync_channel()
