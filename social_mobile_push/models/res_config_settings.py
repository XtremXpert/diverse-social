from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    social_mobile_push_team_id = fields.Char("Identifiant d'équipe Apple", config_parameter='social_mobile_push.team_id')
    social_mobile_push_key_id = fields.Char("Identifiant de la clé APNs", config_parameter='social_mobile_push.key_id')
    social_mobile_push_apns_key = fields.Char(
        "Clé APNs (.p8)", config_parameter='social_mobile_push.apns_key', groups='base.group_system',
        help="Contenu du fichier AuthKey_XXXXXXXXXX.p8 (de -----BEGIN PRIVATE KEY----- à -----END PRIVATE KEY-----).")
    social_mobile_push_bundle_id = fields.Char(
        "Identifiant de l'application", config_parameter='social_mobile_push.bundle_id', default='com.diversecite.app')
    social_mobile_push_fcm_service_account = fields.Char(
        "Compte de service Firebase (JSON)", config_parameter='social_mobile_push.fcm_service_account',
        groups='base.group_system',
        help="Contenu du fichier JSON de la clé du compte de service (console Firebase → Paramètres du projet "
             "→ Comptes de service → Générer une nouvelle clé privée).")
    social_mobile_push_show_sender = fields.Boolean(
        "Nommer l'expéditeur", config_parameter='social_mobile_push.show_sender',
        help="Décoché (recommandé) : « Nouveau message », sans nom, même sur l'écran verrouillé.")
