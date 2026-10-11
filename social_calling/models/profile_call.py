from odoo import models, api, _
from odoo.exceptions import ValidationError


class ClubSocialProfile(models.Model):
    _inherit = 'club_social_profile.profile'

    def action_initiate_video_call(self):
        self.ensure_one()
        return self._initiate_call('video')

    def action_initiate_audio_call(self):
        self.ensure_one()
        return self._initiate_call('audio')

    def _initiate_call(self, call_type):
        self.ensure_one()
        caller = self.env.user
        callee = self.user_id
        if not callee or callee.id == caller.id:
            raise ValidationError(_('You cannot call yourself.'))

        # Check block
        Block = self.env['social_safety.block'].sudo()
        if Block.search([
            '|', '&', ('blocker_id', '=', caller.id), ('blocked_id', '=', callee.id),
                 '&', ('blocker_id', '=', callee.id), ('blocked_id', '=', caller.id),
        ], limit=1):
            raise ValidationError(_('You cannot call this user.'))

        Session = self.env['social_calling.session'].sudo()
        session = Session.create({
            'caller_id': caller.id,
            'callee_id': callee.id,
            'call_type': call_type,
        })

        # Notify callee via bus
        self.env['bus.bus']._sendone(
            callee.partner_id,
            'social_calling/incoming_call',
            {
                'session_id': session.id,
                'caller_name': self.env['club_social_profile.profile']._display_name_for_user(caller),
                'call_type': call_type,
                'room_url': '/my/calls/room/%s' % session.id,
            }
        )

        return {
            'type': 'ir.actions.act_url',
            'url': '/my/calls/room/%s' % session.id,
            'target': 'self',
        }
