from odoo import fields, models, api


class ClubSocialBan(models.Model):
    _name = 'club_social_moderation.ban'
    _description = 'User Ban'
    _order = 'create_date desc'

    profile_id = fields.Many2one(
        'club_social_profile.profile', required=True, ondelete='cascade', index=True,
    )
    banned_by = fields.Many2one('res.users', required=True, default=lambda self: self.env.user)
    reason = fields.Text(required=True)
    banned_until = fields.Datetime(help='Leave empty for permanent ban')
    is_active = fields.Boolean(compute='_compute_is_active', store=True, index=True)
    lifted_at = fields.Datetime()
    lifted_by = fields.Many2one('res.users')

    @api.depends('banned_until', 'lifted_at')
    def _compute_is_active(self):
        now = fields.Datetime.now()
        for ban in self:
            if ban.lifted_at:
                ban.is_active = False
            elif ban.banned_until and ban.banned_until < now:
                ban.is_active = False
            else:
                ban.is_active = True

    def action_lift(self):
        self.write({'lifted_at': fields.Datetime.now(), 'lifted_by': self.env.user.id})

    @api.model
    def cron_expire_bans(self):
        expired = self.search([
            ('is_active', '=', True),
            ('banned_until', '!=', False),
            ('banned_until', '<', fields.Datetime.now()),
        ])
        expired._compute_is_active()
