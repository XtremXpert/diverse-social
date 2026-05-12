from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class SocialMessageThread(models.Model):
    _name = 'social_messaging.thread'
    _description = 'Private Message Thread'
    _order = 'last_message_date desc, id desc'

    participant_ids = fields.Many2many(
        'res.users',
        'social_messaging_thread_participant_rel',
        'thread_id', 'user_id',
        string='Participants',
    )
    message_ids = fields.One2many('social_messaging.message', 'thread_id', string='Messages')
    last_message_date = fields.Datetime(compute='_compute_last_message', store=True)
    last_message_preview = fields.Char(compute='_compute_last_message', store=True)

    @api.depends('message_ids.create_date', 'message_ids.content')
    def _compute_last_message(self):
        for thread in self:
            last = thread.message_ids.sorted('id', reverse=True)[:1]
            thread.last_message_date = last.create_date if last else False
            thread.last_message_preview = (last.content or '')[:80] if last else ''

    def unread_count_for(self, user):
        self.ensure_one()
        return len(self.message_ids.filtered(
            lambda m: m.author_id != user and user not in m.read_by_ids
        ))

    def other_participant(self, user):
        self.ensure_one()
        return self.participant_ids.filtered(lambda u: u != user)[:1]

    @api.model
    def _get_or_create(self, user_ids):
        """Trouve ou crée un fil entre exactement ces utilisateurs."""
        user_ids_sorted = sorted(set(user_ids))
        threads = self.search([('participant_ids', 'in', user_ids_sorted)])
        for thread in threads:
            if sorted(thread.participant_ids.ids) == user_ids_sorted:
                return thread
        return self.create({'participant_ids': [(6, 0, user_ids_sorted)]})

    @api.constrains('participant_ids')
    def _check_participants(self):
        for thread in self:
            if len(thread.participant_ids) < 2:
                raise ValidationError(_('A message thread must have at least 2 participants.'))
