from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    smd_internal_bypass = fields.Boolean(
        string="Utilisateurs internes : écrire à tout membre",
        config_parameter='social_messaging_discuss.internal_bypass',
        help="Les utilisateurs internes (employés) peuvent ouvrir une conversation "
             "avec n'importe quel membre, même hors de leurs connexions, groupes "
             "et cercles. Le blocage (social_safety) reste appliqué.",
    )
