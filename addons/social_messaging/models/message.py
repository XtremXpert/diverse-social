from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


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
    content = fields.Text(required=True)
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

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        Block = self.env['social_safety.block']
        for msg in records:
            thread = msg.thread_id
            if len(thread.participant_ids) == 2:
                other = thread.other_participant(msg.author_id)
                if other and Block.is_blocked(msg.author_id, other):
                    raise UserError(_('Vous ne pouvez pas envoyer un message à cette personne.'))
        return records

    def mark_as_read(self, user=None):
        user = user or self.env.user
        self.write({'read_by_ids': [(4, user.id)]})

    @api.constrains('content')
    def _check_content(self):
        for msg in self:
            if not (msg.content or '').strip():
                raise ValidationError(_('Message content cannot be empty.'))
