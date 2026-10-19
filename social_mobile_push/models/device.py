import re

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

TOKEN_RE = re.compile(r'^[0-9a-f]{64,200}$')
# Jeton d'enregistrement FCM : sensible à la casse, ~150 à 200 caractères.
FCM_TOKEN_RE = re.compile(r'^[A-Za-z0-9_:-]{100,4096}$')


KINDS = ('alert', 'voip')
PLATFORMS = ('apns', 'fcm')


class SocialMobileDevice(models.Model):
    """Téléphone qui reçoit les notifications d'un membre : iPhone (APNs) ou Android (FCM).

    Un même iPhone a deux jetons : ``alert`` pour les notifications, ``voip`` (PushKit) pour faire
    sonner les appels. Ce sont deux enregistrements : un jeton refusé par Apple n'emporte pas l'autre.
    Un téléphone Android n'a qu'un jeton FCM (``alert``), qui sert aussi à faire sonner les appels."""
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
    platform = fields.Selection([('apns', "iPhone (APNs)"), ('fcm', "Android (FCM)")],
                                required=True, default='apns', readonly=True, index=True)
    last_seen = fields.Datetime(readonly=True)
    active = fields.Boolean(default=True)

    _token_uniq = models.Constraint('UNIQUE(token)', "Ce jeton d'appareil est déjà enregistré.")

    @api.model
    def _api_register(self, token, environment, kind='alert', platform='apns'):
        """Enregistre le téléphone de l'utilisateur courant. Un jeton déjà connu (même téléphone,
        autre compte) est réattribué : les notifications d'un membre n'arrivent jamais chez un autre."""
        if platform not in PLATFORMS:
            raise ValidationError(_("Plateforme invalide."))
        if platform == 'fcm':
            token = (token or '').strip()
            if not FCM_TOKEN_RE.match(token):
                raise ValidationError(_("Jeton d'appareil invalide."))
            if kind != 'alert':
                raise ValidationError(_("Type de jeton invalide."))
            environment = 'production'  # un seul serveur FCM
        else:
            token = (token or '').strip().lower()
            if not TOKEN_RE.match(token):
                raise ValidationError(_("Jeton d'appareil invalide."))
        if environment not in ('production', 'sandbox'):
            raise ValidationError(_("Environnement invalide."))
        if kind not in KINDS:
            raise ValidationError(_("Type de jeton invalide."))
        Device = self.sudo().with_context(active_test=False)
        vals = {'user_id': self.env.uid, 'environment': environment, 'kind': kind, 'platform': platform,
                'last_seen': fields.Datetime.now(), 'active': True}
        device = Device.search([('token', '=', token)], limit=1)
        if device:
            device.write(vals)
        else:
            device = Device.create(dict(vals, token=token))
        return device

    @api.model
    def _api_unregister(self, token=None):
        """Retire le téléphone (déconnexion) ; sans jeton, tous les appareils de l'utilisateur courant.
        Un jeton FCM garde sa casse, un jeton APNs est en minuscules."""
        domain = [('user_id', '=', self.env.uid)]
        if token:
            token = token.strip()
            domain.append(('token', 'in', list({token, token.lower()})))
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
        """Envoie aussitôt la notification à cet appareil et dit ce qu'Apple ou Google a répondu."""
        self.ensure_one()
        self._check_system()
        if self.kind == 'voip':
            raise UserError(_("Ce jeton sert à faire sonner les appels : l'essai se fait sur le jeton « Notifications »."))
        Queue = self.env['social_mobile.push_queue'].sudo()
        device = self.sudo()
        if device.platform == 'fcm':
            config = Queue._fcm_config()
            if not config:
                raise UserError(_("Le compte de service Firebase n'est pas réglé : voir Application mobile → Configuration → Paramètres."))
            with Queue._http_client() as client:
                outcome = Queue._deliver_fcm(client, device, config, {'type': 'alert', 'title': title, 'body': body})
            return self._test_result(device, outcome, "Google")
        config = Queue._config()
        if not config:
            raise UserError(_("La clé APNs n'est pas réglée : voir Application mobile → Configuration → Paramètres."))
        payload = {'aps': {'alert': {'title': title, 'body': body}, 'sound': 'default'}}
        with Queue._http_client() as client:
            outcome = Queue._deliver(client, device, config, payload, None)
        return self._test_result(device, outcome, "Apple")

    def _test_result(self, device, outcome, service):
        """Ce que le service (Apple ou Google) a répondu à la notification d'essai."""
        if outcome == 'ok' and device.exists():
            kind, message = 'success', _("Envoyée : elle devrait apparaître sur le téléphone dans quelques secondes.")
        elif outcome == 'ok':
            kind, message = 'warning', _("%(service)s ne reconnaît plus ce jeton : l'appareil a été retiré. "
                                         "Rouvrez l'application sur le téléphone pour le réenregistrer.", service=service)
        elif outcome == 'stop' and service == "Google":
            kind, message = 'danger', _("Google refuse la configuration : vérifiez le compte de service Firebase.")
        elif outcome == 'stop':
            kind, message = 'danger', _("Apple refuse la configuration : vérifiez l'équipe, la clé et le bundle.")
        else:
            kind, message = 'danger', _("%(service)s est injoignable pour l'instant. Réessayez plus tard.", service=service)
        return {'type': 'ir.actions.client', 'tag': 'display_notification',
                'params': {'title': _("Notification d'essai"), 'message': message, 'type': kind,
                           'sticky': kind != 'success', 'next': {'type': 'ir.actions.act_window_close'}}}
