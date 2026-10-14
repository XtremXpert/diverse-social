from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    social_mobile_install_url = fields.Char(
        "Lien d'installation de l'application", config_parameter='social_mobile.install_url',
        help="Lien App Store (non listé) affiché en QR code par les membres pour faire installer l'application.")
    social_mobile_membership_type_id = fields.Many2one(
        'club_membership.type', "Adhésion des nouveaux membres",
        config_parameter='social_mobile.membership_type_id',
        help="Adhésion créée et activée quand un membre parraine un nouveau venu dans l'application. "
             "Vide : « Membre régulier ».")
    social_mobile_key_days = fields.Integer(
        "Durée des clés de l'application (jours)", config_parameter='social_mobile.key_days', default=180)
    social_mobile_review_user_id = fields.Many2one(
        'res.users', "Compte de démonstration (examen Apple)", config_parameter='social_mobile.review_user_id',
        help="Compte ouvert par le code d'examen. À réserver à des données de démonstration.")
    social_mobile_review_code = fields.Char(
        "Code d'examen Apple", config_parameter='social_mobile.review_code',
        help="Saisi dans l'application à la place du parrainage, pour l'examen de l'App Store. "
             "Videz-le une fois l'application approuvée.")
