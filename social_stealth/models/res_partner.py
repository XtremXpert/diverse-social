from odoo import api, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    def _stealth_viewer_active(self):
        """True quand le spectateur courant doit voir les pseudonymes.

        Clé sur ``env.user`` (l'uid survit au ``sudo()``, donc fiable dans
        les contrôleurs portail qui élèvent leurs lectures). Les internes
        et modérateurs voient les vrais noms ; tout le reste (membres,
        portail, public) voit les pseudonymes.
        """
        ctx = self.env.context.get('stealth_display')
        if ctx is not None:
            return bool(ctx)
        user = self.env.user
        if user.has_group('base.group_user') \
                or user.has_group('social_base.group_social_moderator'):
            return False
        return True

    @api.depends_context('uid', 'stealth_display')
    def _compute_display_name(self):
        # Spectateur privilégié → comportement standard, zéro coût ajouté.
        if not self._stealth_viewer_active():
            return super()._compute_display_name()

        # Une seule requête groupée : pseudonymes des partners du batch.
        # Le membre se voit toujours lui-même sous son vrai nom.
        profiles = self.env['club_social_profile.profile'].sudo().search([
            ('user_id.partner_id', 'in', self.ids),
            ('stealth_name', '!=', False),
        ])
        me_pid = self.env.user.partner_id.id
        alias = {
            p.user_id.partner_id.id: p.stealth_name
            for p in profiles
            if p.user_id.partner_id and p.user_id.partner_id.id != me_pid
        }
        plain = self.filtered(lambda r: r.id not in alias)
        if plain:
            super(ResPartner, plain)._compute_display_name()
        for rec in self - plain:
            rec.display_name = alias[rec.id]


class ResUsers(models.Model):
    _inherit = 'res.users'

    # res.users ne délègue PAS display_name au partner (compute par défaut
    # de BaseModel sur user.name) : on applique la même interception ici.
    # On ne délègue pas non plus à partner.display_name pour ne pas hériter
    # de ses préfixes (société commerciale) dans les dropdowns backend.
    @api.depends_context('uid', 'stealth_display')
    def _compute_display_name(self):
        if not self.env['res.partner']._stealth_viewer_active():
            return super()._compute_display_name()
        profiles = self.env['club_social_profile.profile'].sudo().search([
            ('user_id', 'in', self.ids),
            ('stealth_name', '!=', False),
        ])
        me = self.env.user.id
        alias = {
            p.user_id.id: p.stealth_name
            for p in profiles if p.user_id.id != me
        }
        plain = self.filtered(lambda r: r.id not in alias)
        if plain:
            super(ResUsers, plain)._compute_display_name()
        for rec in self - plain:
            rec.display_name = alias[rec.id]
