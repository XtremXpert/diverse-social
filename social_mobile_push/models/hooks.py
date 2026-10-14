from odoo import api, models


class DiscussChannel(models.Model):
    _inherit = 'discuss.channel'

    def message_post(self, *, message_type="notification", **kwargs):
        message = super().message_post(message_type=message_type, **kwargs)
        if message_type == 'comment':
            self._mobile_push_new_message(message)
        return message

    def _mobile_push_new_message(self, message):
        """Notifie les autres membres d'une conversation mobile (à deux ou de relation)."""
        Queue = self.env['social_mobile.push_queue']
        for channel in self.sudo():
            is_mobile = channel.channel_type == 'chat' or (channel.channel_type == 'group' and channel._mobile_relation())
            if not is_mobile:
                continue  # autres canaux Discuss : jamais de notification mobile
            author = message.author_id.user_ids[:1]
            recipients = channel.channel_member_ids.partner_id.filtered(
                lambda p: p != message.author_id).user_ids
            Queue._enqueue(recipients, 'message', channel=channel, author=author)


class SocialRelationMember(models.Model):
    _inherit = 'social_relation.member'

    @api.model_create_multi
    def create(self, vals_list):
        members = super().create(vals_list)
        members._mobile_push_state_change()
        return members

    def write(self, vals):
        before = {m.id: m.state for m in self}
        res = super().write(vals)
        if 'state' in vals:
            self.filtered(lambda m: before.get(m.id) != m.state)._mobile_push_state_change()
        return res

    def _mobile_push_state_change(self):
        """Invitation reçue → l'invité ; proposition à approuver → les autres membres."""
        Queue = self.env['social_mobile.push_queue']
        for member in self.sudo():
            relation = member.relation_id
            if member.state == 'invited':
                Queue._enqueue(member.user_id, 'relation_invite', relation=relation)
            elif member.state == 'proposed':
                approvers = relation.accepted_user_ids - member.approval_user_ids
                if approvers:
                    Queue._enqueue(approvers, 'relation_proposal', relation=relation)


class ResUsersApikeys(models.Model):
    _inherit = 'res.users.apikeys'

    @api.model
    def _social_mobile_revoke_all(self):
        """Suppression du compte : plus de notifications vers ses iPhone."""
        self.env['social_mobile.device']._api_unregister()
        return super()._social_mobile_revoke_all()
