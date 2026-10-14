import re

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

TOKEN_RE = re.compile(r'^[0-9a-f]{64,200}$')


class SocialMobileDevice(models.Model):
    """iPhone qui reçoit les notifications d'un membre (jeton APNs)."""
    _name = 'social_mobile.device'
    _description = "Appareil mobile (notifications)"
    _order = 'last_seen desc'
    _rec_name = 'user_id'

    user_id = fields.Many2one('res.users', required=True, index=True, ondelete='cascade', readonly=True)
    token = fields.Char(required=True, readonly=True, copy=False, groups='base.group_system')
    environment = fields.Selection([('production', "Production"), ('sandbox', "Développement")],
                                   required=True, default='production', readonly=True)
    last_seen = fields.Datetime(readonly=True)
    active = fields.Boolean(default=True)

    _token_uniq = models.Constraint('UNIQUE(token)', "Ce jeton d'appareil est déjà enregistré.")

    @api.model
    def _api_register(self, token, environment):
        """Enregistre l'iPhone de l'utilisateur courant. Un jeton déjà connu (même téléphone,
        autre compte) est réattribué : les notifications d'un membre n'arrivent jamais chez un autre."""
        token = (token or '').strip().lower()
        if not TOKEN_RE.match(token):
            raise ValidationError(_("Jeton d'appareil invalide."))
        if environment not in ('production', 'sandbox'):
            raise ValidationError(_("Environnement invalide."))
        Device = self.sudo().with_context(active_test=False)
        vals = {'user_id': self.env.uid, 'environment': environment, 'last_seen': fields.Datetime.now(), 'active': True}
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
