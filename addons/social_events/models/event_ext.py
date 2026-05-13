from odoo import models, fields, api, _
from odoo.exceptions import UserError


class EventEvent(models.Model):
    _inherit = 'event.event'

    social_visibility = fields.Selection([
        ('members', 'All Members'),
        ('circles', 'Specific Circles'),
    ], string='Social Visibility', default='members',
       help='Members: any club member can see and register.\n'
            'Specific Circles: only users in the chosen circles can see and register.')

    allowed_circle_ids = fields.Many2many(
        'social_circles.circle',
        'social_events_circle_rel',
        'event_id', 'circle_id',
        string='Allowed Circles',
        help="Only members of these circles can see and register for this event. "
             "Circles are taken from the organizer's profile.",
    )

    organizer_user_id = fields.Many2one(
        'res.users', string='Organizer (Member)',
        default=lambda self: self.env.user,
        index=True,
        help='Club member responsible for this event.',
    )

    def _check_social_access(self, user=None):
        """Return True if user may see/register for this event."""
        self.ensure_one()
        user = user or self.env.user
        if not self.social_visibility:
            return True
        if self.social_visibility == 'members':
            return user.has_group('social_base.group_social_user')
        if self.social_visibility == 'circles':
            return any(circle.has_member(user) for circle in self.allowed_circle_ids)
        return False

    @api.constrains('social_visibility', 'allowed_circle_ids')
    def _check_circles_set(self):
        for event in self:
            if event.social_visibility == 'circles' and not event.allowed_circle_ids:
                raise UserError(_(
                    'Please select at least one circle for circle-restricted visibility.'
                ))
