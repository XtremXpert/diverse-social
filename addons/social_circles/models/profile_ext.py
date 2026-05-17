from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

# Default circle automatically created for every new profile.
# Used as the landing circle for accepted friend connections.
DEFAULT_CIRCLE_NAME = 'Connaissances'
DEFAULT_CIRCLE_SEQUENCE = 100  # low priority — shows after user-defined circles


class ClubSocialProfile(models.Model):
    _inherit = 'club_social_profile.profile'

    circle_ids = fields.One2many(
        'social_circles.circle', 'profile_id', string='Circles',
    )
    circle_count = fields.Integer(compute='_compute_circle_count')

    # ── Visibility tiers ─────────────────────────────────────────────────────
    # Who can see the detailed sections (bio, orientation, looking_for, location)
    detailed_visibility = fields.Selection([
        ('members', 'All Members'),
        ('circles', 'Any Circle'),
        ('specific', 'Specific Circle'),
        ('connections', 'Connections Only'),
        ('private', 'Only Me'),
    ], default='members', required=True,
        string='Detailed Info Visible To',
        help='Controls who can read bio, orientation, location, looking-for.')

    detailed_visibility_circle_id = fields.Many2one(
        'social_circles.circle',
        string='Specific Circle',
        domain="[('profile_id', '=', id)]",
        help='Only visible when Detailed Info = Specific Circle.',
    )

    @api.depends('circle_ids')
    def _compute_circle_count(self):
        for p in self:
            p.circle_count = len(p.circle_ids)

    @api.constrains('detailed_visibility', 'detailed_visibility_circle_id')
    def _check_specific_circle(self):
        for p in self:
            if p.detailed_visibility == 'specific' and not p.detailed_visibility_circle_id:
                raise ValidationError(_(
                    'Please select a circle when using "Specific Circle" visibility.'
                ))
            if p.detailed_visibility_circle_id and p.detailed_visibility_circle_id.profile_id != p:
                raise ValidationError(_('The selected circle must belong to this profile.'))

    # ── API ───────────────────────────────────────────────────────────────────

    def get_circles_for(self, viewer_user):
        """Return circles of this profile that contain viewer_user."""
        self.ensure_one()
        return self.circle_ids.filtered(lambda c: viewer_user in c.member_ids)

    def is_in_any_circle(self, viewer_user):
        self.ensure_one()
        return bool(self.get_circles_for(viewer_user))

    def can_see_detailed_info(self, viewer_user):
        """Return True if viewer_user is allowed to see sensitive profile sections."""
        self.ensure_one()
        if viewer_user == self.user_id:
            return True

        v = self.detailed_visibility
        if v == 'private':
            return False
        if v == 'members':
            return viewer_user.has_group('social_base.group_social_user')
        if v == 'circles':
            return self.is_in_any_circle(viewer_user)
        if v == 'specific':
            circle = self.detailed_visibility_circle_id
            return bool(circle and circle.has_member(viewer_user))
        if v == 'connections':
            return self.env['club_social_profile.connection'].is_connected(
                self.user_id, viewer_user
            )
        return False

    def get_visibility_level_for(self, viewer_user):
        """Return a string label describing the viewer's access tier."""
        self.ensure_one()
        if viewer_user == self.user_id:
            return 'owner'
        circles = self.get_circles_for(viewer_user)
        if circles:
            return 'circle:%s' % ','.join(circles.mapped('name'))
        if self.env['club_social_profile.connection'].is_connected(self.user_id, viewer_user):
            return 'connection'
        if viewer_user.has_group('social_base.group_social_user'):
            return 'member'
        return 'anonymous'

    def ensure_circle(self, name, sequence=10):
        """Return the named circle, creating it if absent."""
        self.ensure_one()
        circle = self.circle_ids.filtered(lambda c: c.name == name)
        if not circle:
            circle = self.env['social_circles.circle'].sudo().create({
                'profile_id': self.id,
                'name': name,
                'sequence': sequence,
            })
        return circle

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        # Provision the default circle for every new profile so that
        # accepted connections have a landing circle immediately.
        Circle = self.env['social_circles.circle'].sudo()
        for profile in records:
            Circle.create({
                'profile_id': profile.id,
                'name': DEFAULT_CIRCLE_NAME,
                'sequence': DEFAULT_CIRCLE_SEQUENCE,
            })
        return records
