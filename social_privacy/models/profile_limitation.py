from odoo import models, fields, api


class ClubSocialProfile(models.Model):
    _inherit = 'club_social_profile.profile'

    processing_restricted = fields.Boolean(
        string='Processing Restricted',
        default=False,
        help='When set, the user\'s data is kept but not actively processed '
             '(hidden from discovery, feed scoring disabled, no new notifications).',
    )
    processing_restriction_reason = fields.Text(
        string='Restriction Reason',
        help='Reason provided by the user or admin for the restriction.',
    )
    processing_restricted_at = fields.Datetime(string='Restricted At')

    def action_restrict_processing(self, reason=''):
        self.ensure_one()
        self.write({
            'processing_restricted': True,
            'processing_restriction_reason': reason or False,
            'processing_restricted_at': fields.Datetime.now(),
        })
        # Log the restriction
        self.env['social_privacy.access_log'].sudo().create({
            'user_id': self.env.user.id,
            'target_user_id': self.user_id.id,
            'model_name': self._name,
            'record_id': self.id,
            'action': 'write',
            'reason': 'Processing restricted: %s' % (reason or 'No reason'),
        })

    def action_lift_restriction(self):
        self.ensure_one()
        self.write({
            'processing_restricted': False,
            'processing_restriction_reason': False,
            'processing_restricted_at': False,
        })
