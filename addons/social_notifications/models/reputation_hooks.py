from odoo import _, api, models


class SocialVouchingNotification(models.Model):
    _inherit = 'social_reputation.vouching'

    @api.model
    def vouch_for(self, newcomer_user, statement=None):
        vouching = super().vouch_for(newcomer_user, statement=statement)
        self.env['club_social_profile.notification']._notify(
            user_id=newcomer_user.id,
            actor_id=self.env.user.id,
            notif_type='vouching_received',
            body=_('%(name)s vouched for you in the community.', name=self.env.user.name),
            ref_model='social_reputation.vouching',
            ref_id=vouching.id,
        )
        return vouching

    def action_withdraw(self, reason=None):
        res = super().action_withdraw(reason=reason)
        Notif = self.env['club_social_profile.notification']
        for vouching in self:
            # Cas d'une invitation cancellée avant signup : pas de newcomer
            # à notifier (et le INSERT échouerait sur user_id NOT NULL).
            if not vouching.newcomer_id:
                continue
            Notif._notify(
                user_id=vouching.newcomer_id.id,
                actor_id=vouching.sponsor_id.id,
                notif_type='vouching_withdrawn',
                body=_('%(name)s withdrew their vouch.', name=vouching.sponsor_id.name),
            )
        return res
