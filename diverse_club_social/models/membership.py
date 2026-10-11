from odoo import models


class ClubMembership(models.Model):
    _inherit = 'club_membership.membership'

    def _sync_social_access(self, grant):
        """Extend the base sync so that activating a membership also flips
        any ``pending_payment`` vouching invitations for the same user into
        ``active`` state. Without this hook, the chain of trust would stay
        in pending_payment forever even after payment lands.

        We do NOT call ``_enforce_chain_of_trust`` on revoke here: a member
        whose membership lapses keeps their vouching rows (and the sponsor's
        commitment). The social_user group is revoked by the parent method.
        """
        super()._sync_social_access(grant)
        if not grant:
            return
        if 'social_reputation.vouching' not in self.env:
            return
        Vouching = self.env['social_reputation.vouching']
        for rec in self:
            if not rec.user_id:
                continue
            pending = Vouching.sudo().search([
                ('newcomer_id', '=', rec.user_id.id),
                ('state', '=', 'pending_payment'),
            ])
            if pending:
                pending.action_activate_after_payment()
