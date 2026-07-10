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

        # Une seule requête groupée : TOUS les profils membres du batch.
        # Pour un spectateur membre, on prend la main complète sur les
        # partners membres : pseudonyme s'il existe (sauf soi-même), sinon
        # le vrai nom — JAMAIS le login. (club_base remplace display_name
        # par le login des partners purement portail pour l'identification
        # backoffice ; laisser passer son super() ré-exposerait le courriel
        # aux membres.) Les partners sans profil gardent le comportement
        # standard, club_base inclus.
        profiles = self.env['club_social_profile.profile'].sudo().search([
            ('user_id.partner_id', 'in', self.ids),
        ])
        me_pid = self.env.user.partner_id.id
        member = {}
        for p in profiles:
            partner = p.user_id.partner_id
            if not partner:
                continue
            if p.stealth_name and partner.id != me_pid:
                member[partner.id] = p.stealth_name
            else:
                member[partner.id] = p.user_id.sudo().name
        rest = self.filtered(lambda r: r.id not in member)
        if rest:
            super(ResPartner, rest)._compute_display_name()
        for rec in self - rest:
            rec.display_name = member[rec.id]


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
        ])
        me = self.env.user.id
        member = {}
        for p in profiles:
            if p.stealth_name and p.user_id.id != me:
                member[p.user_id.id] = p.stealth_name
            else:
                member[p.user_id.id] = p.user_id.sudo().name
        rest = self.filtered(lambda r: r.id not in member)
        if rest:
            super(ResUsers, rest)._compute_display_name()
        for rec in self - rest:
            rec.display_name = member[rec.id]
