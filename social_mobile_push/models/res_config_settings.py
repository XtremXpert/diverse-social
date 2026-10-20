from odoo import _, api, fields, models

from . import fcm


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
    # Téléversement du même fichier JSON : son contenu passe dans le champ ci-dessus, puis le fichier
    # est oublié (rien ne reste dans l'enregistrement temporaire des réglages).
    social_mobile_push_fcm_file = fields.Binary(
        "Fichier du compte de service", attachment=False, groups='base.group_system')
    social_mobile_push_show_sender = fields.Boolean(
        "Nommer l'expéditeur", config_parameter='social_mobile_push.show_sender',
        help="Décoché (recommandé) : « Nouveau message », sans nom, même sur l'écran verrouillé.")

    @api.onchange('social_mobile_push_fcm_file')
    def _onchange_social_mobile_push_fcm_file(self):
        if not self.social_mobile_push_fcm_file:
            return None
        data = self.social_mobile_push_fcm_file.content
        self.social_mobile_push_fcm_file = False
        try:
            text = data.decode('utf-8')
        except UnicodeDecodeError:
            text = ''
        if not fcm.parse_service_account(text):
            return {'warning': {
                'title': _("Fichier refusé"),
                'message': _("Ce n'est pas la clé JSON d'un compte de service Firebase "
                             "(project_id, client_email et private_key attendus)."),
            }}
        self.social_mobile_push_fcm_service_account = text
        return None
