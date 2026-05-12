from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class ClubSocialConnection(models.Model):
    _name = 'club_social_profile.connection'
    _description = 'Social Connection'
    _order = 'create_date desc'

    user_id = fields.Many2one('res.users', required=True, index=True)
    connected_user_id = fields.Many2one('res.users', required=True, index=True)
    connection_type = fields.Selection([
        ('friend', 'Friend'),
        ('following', 'Following'),
    ], required=True, default='friend')
    state = fields.Selection([
        ('pending', 'Pending'),
        ('accepted', 'Accepted'),
        ('rejected', 'Rejected'),
        ('blocked', 'Blocked'),
    ], default='pending', required=True)
    create_date = fields.Datetime('Requested', readonly=True)
    accepted_date = fields.Datetime()

    @api.constrains('user_id', 'connected_user_id')
    def _check_unique_connection(self):
        for conn in self:
            if conn.user_id == conn.connected_user_id:
                raise ValidationError(_('Cannot connect to yourself'))
            existing = self.search([
                ('user_id', '=', conn.user_id.id),
                ('connected_user_id', '=', conn.connected_user_id.id),
                ('id', '!=', conn.id),
            ])
            if existing:
                raise ValidationError(_('Connection already exists'))

    def action_accept(self):
        self.ensure_one()
        if self.connection_type == 'friend':
            # Créer la connexion réciproque
            self.env['club_social_profile.connection'].create({
                'user_id': self.connected_user_id.id,
                'connected_user_id': self.user_id.id,
                'connection_type': 'friend',
                'state': 'accepted',
                'accepted_date': fields.Datetime.now(),
            })
        self.write({'state': 'accepted', 'accepted_date': fields.Datetime.now()})

    def action_reject(self):
        self.write({'state': 'rejected'})

    def action_block(self):
        self.write({'state': 'blocked'})

    def action_unblock(self):
        self.write({'state': 'rejected'})

    def action_unfriend(self):
        if self.connection_type == 'friend':
            reciprocal = self.search([
                ('user_id', '=', self.connected_user_id.id),
                ('connected_user_id', '=', self.user_id.id),
            ])
            reciprocal.unlink()
        self.unlink()

    @api.model
    def is_connected(self, user1, user2):
        return bool(self.search([
            ('user_id', '=', user1.id),
            ('connected_user_id', '=', user2.id),
            ('state', '=', 'accepted'),
        ], limit=1))
