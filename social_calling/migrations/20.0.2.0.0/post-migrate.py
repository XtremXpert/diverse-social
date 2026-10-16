"""Retrait de la variante Jitsi : efface les appels et leurs traces.

À la mise à jour, Odoo retire les modèles disparus (ir.model) mais laisse leurs
tables. Sans le cron de purge (Loi 25), l'historique d'appels et le chat y
resteraient indéfiniment : on supprime donc les données et les tables.
"""
from odoo import SUPERUSER_ID, api

MODELS = ('social_calling.session', 'social_calling.message')
TABLES = (
    'social_calling_message',
    'social_calling_session_participant_rel',
    'social_calling_session',
)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    env['ir.attachment'].search([('res_model', 'in', MODELS)]).unlink()
    env['mail.message'].search([('model', 'in', MODELS)]).unlink()
    env['mail.followers'].search([('res_model', 'in', MODELS)]).unlink()
    env['mail.activity'].search([('res_model', 'in', MODELS)]).unlink()
    for table in TABLES:
        cr.execute(f'DROP TABLE IF EXISTS "{table}" CASCADE')
