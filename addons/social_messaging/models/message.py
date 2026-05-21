from odoo import api, fields, models, _
from odoo.exceptions import UserError


class SocialMessage(models.Model):
    _name = 'social_messaging.message'
    _description = 'Private Message'
    _order = 'create_date asc, id asc'

    thread_id = fields.Many2one(
        'social_messaging.thread', required=True, ondelete='cascade', index=True,
    )
    author_id = fields.Many2one(
        'res.users', required=True, default=lambda self: self.env.user, index=True,
    )
    content = fields.Text()
    read_by_ids = fields.Many2many(
        'res.users',
        'social_messaging_message_read_rel',
        'message_id', 'user_id',
        string='Read By',
    )
    attachment_ids = fields.One2many(
        'ir.attachment', 'res_id',
        domain=[('res_model', '=', 'social_messaging.message')],
        string='Attachments',
    )
    reaction_ids = fields.One2many(
        'social_messaging.reaction', 'message_id', string='Reactions',
    )

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        Block = self.env['social_safety.block']
        for msg in records:
            thread = msg.thread_id
            if len(thread.participant_ids) == 2:
                other = thread.other_participant(msg.author_id)
                if other and Block.is_blocked(msg.author_id, other):
                    raise UserError(_('You cannot send a message to this person.'))
        # No broadcast here: attachments are attached after create() by the
        # controllers. The controller (or API) is responsible for calling
        # `_broadcast('message_new')` once the message is complete.
        return records

    def mark_as_read(self, user=None):
        user = user or self.env.user
        self.write({'read_by_ids': [(4, user.id)]})
        for msg in self:
            msg._broadcast('message_read', extra={'reader_id': user.id})

    def _broadcast(self, event, extra=None):
        """Broadcast an event to all thread participants via bus.bus.

        Targets each participant's ``res.partner`` channel — the channel that
        Odoo's websocket listens to automatically for the connected user
        (see ``ir_websocket._build_bus_channel_list``).
        """
        self.ensure_one()
        Bus = self.env['bus.bus'].sudo()
        payload = {
            'event': event,
            'thread_id': self.thread_id.id,
            'message_id': self.id,
        }
        if extra:
            payload.update(extra)
        for user in self.thread_id.participant_ids:
            Bus._sendone(user.partner_id, 'social_messaging.update', payload)
