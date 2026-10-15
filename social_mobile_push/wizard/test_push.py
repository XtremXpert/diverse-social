from odoo import _, fields, models
from odoo.exceptions import ValidationError

# Au-delà, l'écran verrouillé tronque le texte.
MAX_BODY = 178


class SocialMobileTestPush(models.TransientModel):
    """Notification d'essai à un appareil, au texte modifiable."""
    _name = 'social_mobile.test_push'
    _description = "Notification d'essai"

    device_id = fields.Many2one('social_mobile.device', "Appareil", required=True, readonly=True, ondelete='cascade')
    user_id = fields.Many2one(related='device_id.user_id', string="Membre")
    title = fields.Char("Titre", required=True, default="Diverse-Cité")
    body = fields.Text("Message", required=True, default=lambda self: _("Notification d'essai"))

    def action_send(self):
        self.ensure_one()
        title, body = (self.title or '').strip(), (self.body or '').strip()
        if not title or not body:
            raise ValidationError(_("Le titre et le message sont obligatoires."))
        if len(body) > MAX_BODY:
            raise ValidationError(_("Message trop long (%(max)s caractères au plus).", max=MAX_BODY))
        return self.device_id._send_test(title, body)
