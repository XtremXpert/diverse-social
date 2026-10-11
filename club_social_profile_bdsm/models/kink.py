from odoo import fields, models, api, _
from odoo.exceptions import ValidationError


class ClubSocialKink(models.Model):
    _name = 'club_social_profile_bdsm.kink'
    _description = 'BDSM Kink / Interest'
    _order = 'name'

    name = fields.Char(required=True, translate=True)
    description = fields.Text()
    active = fields.Boolean(default=True)
    profile_count = fields.Integer(compute='_compute_profile_count', string='Interested Members')

    def _compute_profile_count(self):
        KinkLevel = self.env['club_social_profile_bdsm.kink_level']
        for kink in self:
            kink.profile_count = KinkLevel.sudo().search_count([('kink_id', '=', kink.id)])


class ClubSocialKinkLevel(models.Model):
    _name = 'club_social_profile_bdsm.kink_level'
    _description = 'Interest Level per Kink'
    _order = 'kink_id'

    profile_id = fields.Many2one(
        'club_social_profile.profile', required=True, ondelete='cascade', index=True,
    )
    kink_id = fields.Many2one(
        'club_social_profile_bdsm.kink', required=True, ondelete='cascade',
    )
    level = fields.Selection([
        ('curieux', 'Curious'),
        ('soft', 'Soft yes'),
        ('oui', 'Yes'),
        ('expert', 'Expert'),
    ], required=True, default='curieux')

    _unique_profile_kink = models.Constraint(
        'UNIQUE(profile_id, kink_id)',
        'One interest level per kink and profile.',
    )


class ClubSocialKinkRequest(models.Model):
    _name = 'club_social_profile_bdsm.kink_request'
    _description = 'Kink Addition Request'
    _order = 'create_date desc'

    name = fields.Char(string='Requested Kink', required=True)
    description = fields.Text(string='Description / Context')
    requester_id = fields.Many2one(
        'res.users', required=True, default=lambda self: self.env.user, ondelete='cascade',
    )
    state = fields.Selection([
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ], default='pending', required=True)
    kink_id = fields.Many2one('club_social_profile_bdsm.kink', readonly=True)
    rejection_reason = fields.Char()
    processed_by = fields.Many2one('res.users', readonly=True)

    def action_approve(self):
        self.ensure_one()
        existing = self.env['club_social_profile_bdsm.kink'].search(
            [('name', '=ilike', self.name)], limit=1
        )
        kink = existing or self.env['club_social_profile_bdsm.kink'].create({
            'name': self.name,
            'description': self.description,
        })
        self.write({'state': 'approved', 'kink_id': kink.id, 'processed_by': self.env.user.id})

    def action_reject(self):
        self.ensure_one()
        if not self.rejection_reason:
            raise ValidationError(_('Please provide a rejection reason.'))
        self.write({'state': 'rejected', 'processed_by': self.env.user.id})
