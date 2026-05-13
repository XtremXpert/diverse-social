from odoo import _, models


class SocialNegotiationNotification(models.Model):
    _inherit = 'social_negotiation.negotiation'

    def action_share(self):
        res = super().action_share()
        Notif = self.env['club_social_profile.notification']
        for neg in self:
            Notif._notify(
                user_id=neg.partner_id.id,
                actor_id=neg.initiator_id.id,
                notif_type='negotiation_shared',
                body=_('%(name)s vous a partagé un document de négociation.',
                        name=neg.initiator_id.name),
                ref_model='social_negotiation.negotiation',
                ref_id=neg.id,
            )
        return res

    def action_sign(self):
        res = super().action_sign()
        Notif = self.env['club_social_profile.notification']
        for neg in self:
            if neg.is_fully_signed:
                # Les deux ont signé : notifier les deux parties
                for uid, actor_id in [
                    (neg.initiator_id.id, neg.partner_id.id),
                    (neg.partner_id.id, neg.initiator_id.id),
                ]:
                    Notif._notify(
                        user_id=uid,
                        actor_id=actor_id,
                        notif_type='negotiation_active',
                        body=_('Votre document de négociation est maintenant actif.'),
                        ref_model='social_negotiation.negotiation',
                        ref_id=neg.id,
                    )
            else:
                # Première signature : notifier l'autre partie
                other_id = (
                    neg.partner_id.id
                    if self.env.user == neg.initiator_id
                    else neg.initiator_id.id
                )
                Notif._notify(
                    user_id=other_id,
                    actor_id=self.env.user.id,
                    notif_type='negotiation_signed',
                    body=_('%(name)s a signé le document de négociation.',
                            name=self.env.user.name),
                    ref_model='social_negotiation.negotiation',
                    ref_id=neg.id,
                )
        return res
