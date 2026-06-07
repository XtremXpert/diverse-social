from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    """Backfill : crée un canal Discuss de groupe pour chaque groupe existant
    qui n'en a pas encore (la création auto ne couvre que les nouveaux groupes)."""
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    groups = env['social_group.group'].search([('discuss_channel_id', '=', False)])
    for group in groups:
        group._get_or_create_discuss_channel()
