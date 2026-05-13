from odoo import models, fields, api, _
from odoo.exceptions import UserError


class ClubSocialProfile(models.Model):
    _inherit = 'club_social_profile.profile'

    # ── Panic mode ────────────────────────────────────────────────────────────
    panic_mode = fields.Boolean(
        'Panic Mode',
        default=False,
        help='When active: profile hidden from non-connections, no new contact requests accepted.',
    )
    panic_activated_at = fields.Datetime('Panic Activated At', readonly=True)
    _panic_saved_visibility = fields.Char(
        'Saved Visibility (panic)', default='members',
    )

    def action_panic(self):
        """Go dark: hide from discovery, block new contact requests."""
        self.ensure_one()
        if self.user_id != self.env.user:
            raise UserError(_('You can only activate panic mode on your own profile.'))
        if self.panic_mode:
            return
        self.write({
            'panic_mode': True,
            'panic_activated_at': fields.Datetime.now(),
            '_panic_saved_visibility': self.visibility,
            'visibility': 'connections',
        })

    def action_panic_lift(self):
        """Come back: restore previous visibility."""
        self.ensure_one()
        if self.user_id != self.env.user:
            raise UserError(_('You can only deactivate panic mode on your own profile.'))
        saved = self._panic_saved_visibility or 'members'
        self.write({
            'panic_mode': False,
            'panic_activated_at': False,
            'visibility': saved,
        })

    # ── Block helpers ─────────────────────────────────────────────────────────

    def has_blocked(self, user):
        """True if this profile's owner has blocked user."""
        self.ensure_one()
        return bool(self.env['social_safety.block'].sudo().search([
            ('blocker_id', '=', self.user_id.id),
            ('blocked_id', '=', user.id),
        ], limit=1))

    def is_blocked_by(self, user):
        """True if user has blocked this profile's owner."""
        self.ensure_one()
        return bool(self.env['social_safety.block'].sudo().search([
            ('blocker_id', '=', user.id),
            ('blocked_id', '=', self.user_id.id),
        ], limit=1))

    def is_safe_to_contact(self, sender_user):
        """False if blocked in either direction or in panic mode."""
        self.ensure_one()
        if self.panic_mode:
            connected = self.env['club_social_profile.connection'].is_connected(
                self.user_id, sender_user
            )
            if not connected:
                return False
        return not self.env['social_safety.block'].is_blocked(self.user_id, sender_user)

    def action_block_user(self, target_user, reason=None):
        """Block target_user from this profile's context."""
        self.ensure_one()
        if self.user_id != self.env.user:
            raise UserError(_('You can only block users from your own profile.'))
        self.env['social_safety.block'].block_user(target_user, reason=reason)

    def action_unblock_user(self, target_user):
        self.ensure_one()
        if self.user_id != self.env.user:
            raise UserError(_('You can only unblock users from your own profile.'))
        self.env['social_safety.block'].unblock_user(target_user)

    def action_mute_user(self, target_user, until=None):
        self.ensure_one()
        if self.user_id != self.env.user:
            raise UserError(_('You can only mute users from your own profile.'))
        self.env['social_safety.mute'].mute_user(target_user, until=until)

    def action_unmute_user(self, target_user):
        self.ensure_one()
        if self.user_id != self.env.user:
            raise UserError(_('You can only unmute users from your own profile.'))
        self.env['social_safety.mute'].unmute_user(target_user)
