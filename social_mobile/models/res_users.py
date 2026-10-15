from odoo import _, models


class ResUsers(models.Model):
    _inherit = 'res.users'

    def _social_mobile_sponsor_refusal(self):
        """Raison pour laquelle ce membre ne peut pas parrainer, ou ``None`` s'il le peut.

        Un parrain doit être membre du réseau, avec une adhésion active et au moins un parrain
        actif (chaîne de confiance), et ne pas être banni. Les administrateurs en sont exemptés
        (ils amorcent la chaîne)."""
        self.ensure_one()
        if self.has_group('base.group_system'):
            return None
        if not self.has_group('social_base.group_social_user'):
            return _("Seul un membre du réseau peut parrainer.")
        Membership = self.env['club_membership.membership'].sudo()
        if not Membership.search_count([('partner_id', '=', self.partner_id.id), ('state', '=', 'active')], limit=1):
            return _("Votre adhésion n'est pas active.")
        if not self.env['social_reputation.vouching'].sudo().has_active_vouching(self):
            return _("Vous n'avez plus de parrain actif.")
        profile = self.env['club_social_profile.profile'].sudo().search([('user_id', '=', self.id)], limit=1)
        if profile and profile.is_banned:
            return _("Votre compte est suspendu.")
        return None

    def _social_mobile_login_refusal(self):
        """Raison pour laquelle ce compte existant ne peut pas ouvrir l'application, ou ``None``.

        Il lui faut un parrain actif enregistré, comme à tout membre entré par le parrainage.
        Les administrateurs en sont exemptés. Ne s'appelle qu'une fois l'identité prouvée : le
        message révèle que le compte existe."""
        self.ensure_one()
        profile = self.env['club_social_profile.profile'].sudo().search([('user_id', '=', self.id)], limit=1)
        if profile and profile.is_banned:
            return _("Votre compte est suspendu.")
        if self.has_group('base.group_system'):
            return None
        if not self.env['social_reputation.vouching'].sudo().search_count(
                [('newcomer_id', '=', self.id), ('state', '=', 'active')], limit=1):
            return _("Votre compte n'a pas de parrain enregistré : l'application ne peut pas l'ouvrir. "
                     "Contactez un administrateur du club.")
        return None
