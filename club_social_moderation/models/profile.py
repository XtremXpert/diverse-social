from odoo import fields, models, api


class ClubSocialProfileModeration(models.Model):
    """Extends club_social_profile.profile with moderation fields."""
    _inherit = 'club_social_profile.profile'

    ban_ids = fields.One2many('club_social_moderation.ban', 'profile_id', string='Bans')
    is_shadow_banned = fields.Boolean(default=False, index=True, string='Shadow Banned')
    is_banned = fields.Boolean(
        compute='_compute_is_banned', store=True, index=True, string='Account Suspended',
    )
    ban_reason = fields.Char(compute='_compute_is_banned', store=True, string='Suspension Reason')

    @api.depends('ban_ids.is_active', 'ban_ids.reason')
    def _compute_is_banned(self):
        for profile in self:
            active_ban = profile.ban_ids.filtered('is_active')[:1]
            profile.is_banned = bool(active_ban)
            profile.ban_reason = active_ban.reason if active_ban else False

    def action_ban(self, reason, banned_until=None):
        self.ensure_one()
        self.env['club_social_moderation.ban'].create({
            'profile_id': self.id,
            'reason': reason,
            'banned_until': banned_until,
        })

    def action_shadow_ban(self):
        self.write({'is_shadow_banned': True})

    def action_lift_shadow_ban(self):
        self.write({'is_shadow_banned': False})
