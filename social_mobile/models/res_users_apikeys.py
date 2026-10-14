import datetime

from odoo import api, fields, models
from odoo.addons.base.models.res_users import INDEX_SIZE, KEY_CRYPT_CONTEXT
from odoo.tools import SQL

SCOPE = 'social_mobile'
DEFAULT_KEY_DAYS = 180


class ResUsersApikeysDescription(models.TransientModel):
    _inherit = 'res.users.apikeys.description'

    scope = fields.Selection(selection_add=[(SCOPE, "Application mobile")], ondelete={SCOPE: 'cascade'})


class ResUsersApikeys(models.Model):
    _inherit = 'res.users.apikeys'

    @api.model
    def _social_mobile_generate(self, name):
        """Clé de portée « social_mobile » pour l'utilisateur courant.

        Générée en sudo pour passer outre la durée maximale des groupes (un membre portail n'a
        droit à aucune) : sa portée n'ouvre que /api/social/v1, et l'application la renouvelle
        avant l'échéance."""
        days = self.env['ir.config_parameter'].sudo().get_int('social_mobile.key_days') or DEFAULT_KEY_DAYS
        expiration = fields.Datetime.now() + datetime.timedelta(days=days)
        key = self.sudo()._generate(SCOPE, name, expiration)
        return key, expiration

    @api.model
    def _social_mobile_find(self, key):
        """Clé « social_mobile » ``key`` de l'utilisateur courant (sudo, vide si inconnue)."""
        candidates = self.sudo().search([('user_id', '=', self.env.uid), ('scope', '=', SCOPE)])
        if not candidates or not key:
            return candidates.browse()
        self.env.cr.execute(SQL(
            "SELECT id, key FROM %s WHERE id IN %s AND index = %s",
            SQL.identifier(self._table), tuple(candidates.ids), key[:INDEX_SIZE],
        ))
        return self.sudo().browse([kid for kid, hashed in self.env.cr.fetchall() if KEY_CRYPT_CONTEXT.verify(key, hashed)])

    @api.model
    def _social_mobile_retire(self, key, grace=datetime.timedelta(hours=24)):
        """Raccourcit la clé ``key`` à ``grace`` : si la réponse du renouvellement se perd,
        l'application réessaie avec l'ancienne clé."""
        found = self._social_mobile_find(key)
        deadline = fields.Datetime.now() + grace
        for apikey in found:
            if not apikey.expiration_date or apikey.expiration_date > deadline:
                apikey.expiration_date = deadline
        if found:
            self.env.transaction.invalidate_ormcache()
        return bool(found)

    @api.model
    def _social_mobile_revoke_all(self):
        """Supprime toutes les clés mobiles de l'utilisateur courant (suppression du compte)."""
        keys = self.sudo().search([('user_id', '=', self.env.uid), ('scope', '=', SCOPE)])
        keys.unlink()
        self.env.transaction.invalidate_ormcache()
