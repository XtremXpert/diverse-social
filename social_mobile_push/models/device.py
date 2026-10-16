import re

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

TOKEN_RE = re.compile(r'^[0-9a-f]{64,200}$')


KINDS = ('alert', 'voip')


class SocialMobileDevice(models.Model):
    """iPhone qui reçoit les notifications d'un membre (jeton APNs).

    Un même iPhone a deux jetons : ``alert`` pour les notifications, ``voip`` (PushKit) pour faire
    sonner les appels. Ce sont deux enregistrements : un jeton refusé par Apple n'emporte pas l'autre."""
    _name = 'social_mobile.device'
    _description = "Appareil mobile (notifications)"
    _order = 'last_seen desc'
    _rec_name = 'user_id'

    user_id = fields.Many2one('res.users', required=True, index=True, ondelete='cascade', readonly=True)
    token = fields.Char(required=True, readonly=True, copy=False, groups='base.group_system')
    environment = fields.Selection([('production', "Production"), ('sandbox', "Développement")],
                                   required=True, default='production', readonly=True)
    kind = fields.Selection([('alert', "Notifications"), ('voip', "Appels")],
                            required=True, default='alert', readonly=True, index=True)
    last_seen = fields.Datetime(readonly=True)
    active = fields.Boolean(default=True)

    _token_uniq = models.Constraint('UNIQUE(token)', "Ce jeton d'appareil est déjà enregistré.")

    @api.model
    def _api_register(self, token, environment, kind='alert'):
        """Enregistre l'iPhone de l'utilisateur courant. Un jeton déjà connu (même téléphone,
        autre compte) est réattribué : les notifications d'un membre n'arrivent jamais chez un autre."""
        token = (token or '').strip().lower()
        if not TOKEN_RE.match(token):
            raise ValidationError(_("Jeton d'appareil invalide."))
        if environment not in ('production', 'sandbox'):
            raise ValidationError(_("Environnement invalide."))
        if kind not in KINDS:
            raise ValidationError(_("Type de jeton invalide."))
        Device = self.sudo().with_context(active_test=False)
        vals = {'user_id': self.env.uid, 'environment': environment, 'kind': kind,
                'last_seen': fields.Datetime.now(), 'active': True}
        device = Device.search([('token', '=', token)], limit=1)
        if device:
            device.write(vals)
        else:
            device = Device.create(dict(vals, token=token))
        return device

    @api.model
    def _api_unregister(self, token=None):
        """Retire l'iPhone (déconnexion) ; sans jeton, tous les appareils de l'utilisateur courant."""
        domain = [('user_id', '=', self.env.uid)]
        if token:
            domain.append(('token', '=', (token or '').strip().lower()))
        self.sudo().with_context(active_test=False).search(domain).unlink()

    # ── Essai ────────────────────────────────────────────────────────────────

    def action_send_test(self):
        """Ouvre l'assistant d'envoi d'une notification d'essai à cet appareil."""
        self.ensure_one()
        self._check_system()
        if self.kind == 'voip':
            raise UserError(_("Ce jeton sert à faire sonner les appels : l'essai se fait sur le jeton « Notifications »."))
        return {
            'type': 'ir.actions.act_window',
            'name': _("Notification d'essai"),
            'res_model': 'social_mobile.test_push',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_device_id': self.id},
        }

    def _check_system(self):
        if not self.env.user.has_group('base.group_system'):
            raise AccessError(_("Réservé aux administrateurs."))

    def _send_test(self, title, body):
        """Envoie aussitôt la notification à cet appareil et dit ce qu'Apple a répondu."""
        self.ensure_one()
        self._check_system()
        if self.kind == 'voip':
            raise UserError(_("Ce jeton sert à faire sonner les appels : l'essai se fait sur le jeton « Notifications »."))
        Queue = self.env['social_mobile.push_queue'].sudo()
        config = Queue._config()
        if not config:
            raise UserError(_("La clé APNs n'est pas réglée : voir Application mobile → Configuration → Paramètres."))
        device = self.sudo()
        payload = {'aps': {'alert': {'title': title, 'body': body}, 'sound': 'default'}}
        with Queue._http_client() as client:
            outcome = Queue._deliver(client, device, config, payload, None)
        if outcome == 'ok' and device.exists():
            kind, message = 'success', _("Envoyée : elle devrait apparaître sur l'iPhone dans quelques secondes.")
        elif outcome == 'ok':
            kind, message = 'warning', _("Apple ne reconnaît plus ce jeton : l'appareil a été retiré. "
                                         "Rouvrez l'application sur l'iPhone pour le réenregistrer.")
        elif outcome == 'stop':
            kind, message = 'danger', _("Apple refuse la configuration : vérifiez l'équipe, la clé et le bundle.")
        else:
            kind, message = 'danger', _("Apple est injoignable pour l'instant. Réessayez plus tard.")
        return {'type': 'ir.actions.client', 'tag': 'display_notification',
                'params': {'title': _("Notification d'essai"), 'message': message, 'type': kind,
                           'sticky': kind != 'success', 'next': {'type': 'ir.actions.act_window_close'}}}
