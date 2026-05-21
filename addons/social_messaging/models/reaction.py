from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class SocialMessageReaction(models.Model):
    _name = 'social_messaging.reaction'
    _description = 'Reaction on a Private Message'
    _order = 'create_date asc, id asc'

    message_id = fields.Many2one(
        'social_messaging.message', required=True, ondelete='cascade', index=True,
    )
    user_id = fields.Many2one(
        'res.users', required=True, default=lambda self: self.env.user, index=True,
    )
    emoji = fields.Char(required=True, size=8)

    _unique_user_emoji = models.Constraint(
        'unique(message_id, user_id, emoji)',
        'A user can only react once with the same emoji on a given message.',
    )

    @api.constrains('emoji')
    def _check_emoji(self):
        for rec in self:
            if not (rec.emoji or '').strip():
                raise ValidationError(_('Reaction emoji cannot be empty.'))

    @api.model
    def toggle(self, message_id, emoji):
        """Add the reaction if absent, remove it if already set by the current user.

        Broadcasts ``reaction_update`` on the bus and returns
        ``(action, reaction)`` where ``action`` is ``'added'`` or ``'removed'``.
        """
        message = self.env['social_messaging.message'].sudo().browse(int(message_id))
        if not message.exists():
            raise ValidationError(_('Message not found.'))
        if self.env.user not in message.thread_id.participant_ids:
            raise ValidationError(_('You are not a participant of this thread.'))
        emoji = (emoji or '').strip()
        if not emoji:
            raise ValidationError(_('Emoji required.'))
        existing = self.sudo().search([
            ('message_id', '=', message.id),
            ('user_id', '=', self.env.user.id),
            ('emoji', '=', emoji),
        ], limit=1)
        if existing:
            existing.unlink()
            action = 'removed'
            rec = False
        else:
            rec = self.sudo().create({
                'message_id': message.id,
                'emoji': emoji,
            })
            action = 'added'
        message._broadcast('reaction_update', extra={
            'reaction_action': action,
            'reaction_user_id': self.env.user.id,
            'reaction_emoji': emoji,
        })
        return action, rec
