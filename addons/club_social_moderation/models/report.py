from odoo import fields, models, api
from odoo.exceptions import ValidationError


class ClubSocialReport(models.Model):
    _name = 'club_social_moderation.report'
    _description = 'Content Report'
    _order = 'create_date desc'
    _inherit = ['mail.thread']

    reporter_id = fields.Many2one(
        'res.users', required=True, default=lambda self: self.env.user, ondelete='cascade', index=True,
    )
    ref_model = fields.Selection([
        ('social_base.post', 'Post'),
        ('social_base.comment', 'Comment'),
        ('club_social_profile.profile', 'Profile'),
    ], string='Content Type', required=True)
    ref_id = fields.Integer(string='Content ID', required=True)
    reason = fields.Selection([
        ('spam', 'Spam'),
        ('harcelement', 'Harassment'),
        ('contenu_inapproprie', 'Inappropriate Content'),
        ('mineurs', 'Minors Protection'),
        ('autre', 'Other'),
    ], required=True)
    description = fields.Text(string='Details')
    state = fields.Selection([
        ('pending', 'Pending'),
        ('resolved', 'Resolved — action taken'),
        ('dismissed', 'Dismissed — no action'),
    ], default='pending', required=True, tracking=True)
    resolved_by = fields.Many2one('res.users')
    resolved_at = fields.Datetime()
    resolution_note = fields.Text()

    _unique_report = models.Constraint(
        'UNIQUE(reporter_id, ref_model, ref_id)',
        'You have already reported this content.',
    )

    def action_resolve(self, note=None):
        self.write({
            'state': 'resolved',
            'resolved_by': self.env.user.id,
            'resolved_at': fields.Datetime.now(),
            'resolution_note': note or self.resolution_note,
        })

    def action_dismiss(self, note=None):
        self.write({
            'state': 'dismissed',
            'resolved_by': self.env.user.id,
            'resolved_at': fields.Datetime.now(),
            'resolution_note': note or self.resolution_note,
        })
