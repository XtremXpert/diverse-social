from odoo import api, fields, models


class ClubSocialNotification(models.Model):
    _name = 'club_social_profile.notification'
    _description = 'Social Notification'
    _order = 'create_date desc'
    _rec_name = 'body'

    user_id = fields.Many2one('res.users', required=True, ondelete='cascade', index=True)
    actor_id = fields.Many2one('res.users', required=True, ondelete='cascade')
    type = fields.Selection([
        ('connection_request', 'Connection Request'),
        ('connection_accepted', 'Connection Accepted'),
        ('post_like', 'Post Like'),
        ('post_comment', 'Post Comment'),
        ('comment_reply', 'Comment Reply'),
        ('new_message', 'New Message'),
        ('profile_visit', 'Profile Visit'),
        ('daily_digest', 'Daily Digest'),
    ], required=True, index=True)
    is_read = fields.Boolean(default=False, index=True)
    read_at = fields.Datetime()
    ref_model = fields.Char()
    ref_id = fields.Integer()
    url = fields.Char()
    body = fields.Char()

    @api.model
    def _notify(self, user_id, actor_id, notif_type, body, url=False, ref_model=False, ref_id=False):
        if user_id == actor_id:
            return
        self.sudo().create({
            'user_id': user_id,
            'actor_id': actor_id,
            'type': notif_type,
            'body': body,
            'url': url or False,
            'ref_model': ref_model or False,
            'ref_id': ref_id or 0,
        })

    def action_mark_read(self):
        self.filtered(lambda n: not n.is_read).write({
            'is_read': True,
            'read_at': fields.Datetime.now(),
        })

    @api.model
    def mark_all_read(self, user_id=None):
        uid = user_id or self.env.user.id
        unread = self.search([('user_id', '=', uid), ('is_read', '=', False)])
        unread.write({'is_read': True, 'read_at': fields.Datetime.now()})
        return len(unread)


class ClubSocialDeviceToken(models.Model):
    _name = 'club_social_profile.device_token'
    _description = 'Push Device Token'

    user_id = fields.Many2one('res.users', required=True, ondelete='cascade', index=True)
    token = fields.Char(required=True)
    platform = fields.Selection([
        ('ios', 'iOS (APNs)'),
        ('android', 'Android (FCM)'),
        ('web', 'Web (WebPush)'),
    ], required=True)
    is_active = fields.Boolean(default=True)
    last_used = fields.Datetime()

    _unique_token = models.Constraint(
        'UNIQUE(token)',
        'This token is already registered.',
    )
