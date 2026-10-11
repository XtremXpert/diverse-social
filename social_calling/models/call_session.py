import secrets
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, AccessDenied


class SocialCallingSession(models.Model):
    _name = 'social_calling.session'
    _description = 'Social Calling Session'
    _order = 'create_date desc'
    _inherit = ['mail.thread']

    name = fields.Char(
        string='Call ID',
        required=True,
        default=lambda s: s.env['ir.sequence'].next_by_code('social_calling.session') or _('CALL-???'),
    )

    room_type = fields.Selection([
        ('direct', 'Direct Call (1-to-1)'),
        ('group', 'Group Room (2-20)'),
    ], string='Room Type', default='direct', required=True)

    # For direct calls
    caller_id = fields.Many2one('res.users', string='Caller', ondelete='restrict')
    callee_id = fields.Many2one('res.users', string='Callee', ondelete='restrict')

    # For group rooms
    host_id = fields.Many2one('res.users', string='Host', ondelete='restrict')
    participant_ids = fields.Many2many(
        'res.users',
        'social_calling_session_participant_rel',
        'session_id', 'user_id',
        string='Participants',
    )
    max_participants = fields.Integer(
        string='Max Participants',
        default=20,
        help='Maximum number of participants allowed in this room.',
    )

    call_type = fields.Selection([
        ('video', 'Video'),
        ('audio', 'Audio Only'),
    ], string='Call Type', default='video', required=True)

    state = fields.Selection([
        ('ringing', 'Ringing'),
        ('connected', 'Connected'),
        ('ended', 'Ended'),
        ('missed', 'Missed'),
        ('declined', 'Declined'),
    ], string='Status', default='ringing', required=True, tracking=True)

    room_name = fields.Char(
        string='Room Name',
        required=True,
        default=lambda self: secrets.token_urlsafe(16),
    )
    room_password = fields.Char(
        string='Room Password',
        required=True,
        default=lambda self: secrets.token_urlsafe(8),
    )

    started_at = fields.Datetime(string='Started At')
    ended_at = fields.Datetime(string='Ended At')
    duration_seconds = fields.Integer(
        string='Duration (s)',
        compute='_compute_duration',
        store=True,
    )

    # Jitsi configuration
    def _default_jitsi_server(self):
        # Configurable sans redéploiement via ir.config_parameter. Défaut :
        # l'instance auto-hébergée (conforme Loi 25), pas meet.jit.si.
        return self.env['ir.config_parameter'].sudo().get_str(
            'social_calling.jitsi_server', 'meet.diverse-cite.com')

    jitsi_server = fields.Char(
        string='Jitsi Server',
        default=lambda self: self._default_jitsi_server(),
        help='Domain of the Jitsi server. Configurable via le paramètre système '
             '"social_calling.jitsi_server". Use your own for privacy compliance.',
    )

    # Transcript du chat (mail.thread occupe déjà `message_ids`).
    chat_message_ids = fields.One2many(
        'social_calling.message', 'session_id', string='Chat Transcript',
    )

    @api.depends('started_at', 'ended_at')
    def _compute_duration(self):
        for call in self:
            if call.started_at and call.ended_at:
                call.duration_seconds = int((call.ended_at - call.started_at).total_seconds())
            else:
                call.duration_seconds = 0

    @api.constrains('caller_id', 'callee_id', 'participant_ids')
    def _check_not_blocked(self):
        Block = self.env['social_safety.block'].sudo()
        for call in self:
            if call.room_type == 'direct' and call.caller_id and call.callee_id:
                block = Block.search([
                    '|', '&', ('blocker_id', '=', call.caller_id.id), ('blocked_id', '=', call.callee_id.id),
                         '&', ('blocker_id', '=', call.callee_id.id), ('blocked_id', '=', call.caller_id.id),
                ], limit=1)
                if block:
                    raise ValidationError(_(
                        'You cannot call a user who has blocked you (or whom you have blocked).'
                    ))
            elif call.room_type == 'group' and call.host_id:
                for user in call.participant_ids:
                    block = Block.search([
                        '|', '&', ('blocker_id', '=', call.host_id.id), ('blocked_id', '=', user.id),
                             '&', ('blocker_id', '=', user.id), ('blocked_id', '=', call.host_id.id),
                    ], limit=1)
                    if block:
                        raise ValidationError(_(
                            'One or more participants have been blocked by the host.'
                        ))

    @api.constrains('caller_id', 'callee_id')
    def _check_not_calling_self(self):
        for call in self:
            if call.room_type == 'direct' and call.caller_id == call.callee_id:
                raise ValidationError(_('You cannot call yourself.'))

    @api.constrains('participant_ids', 'max_participants')
    def _check_max_participants(self):
        for room in self:
            if room.room_type == 'group' and len(room.participant_ids) > room.max_participants:
                raise ValidationError(_(
                    'This room has reached its maximum capacity of %(max)s participants.',
                    max=room.max_participants,
                ))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            # Ensure caller/host is the current user unless admin/superuser
            caller = vals.get('caller_id')
            host = vals.get('host_id')
            initiator = caller or host
            is_admin = self.env.user._is_superuser() or self.env.user._is_system()
            if initiator and initiator != self.env.user.id and not is_admin:
                raise AccessDenied()
            # For group rooms, auto-add host to participants
            if vals.get('room_type') == 'group' and 'participant_ids' not in vals:
                host_id = vals.get('host_id', self.env.user.id)
                vals['participant_ids'] = [(4, host_id)]
        return super().create(vals_list)

    def action_connect(self):
        self.ensure_one()
        if self.state != 'ringing':
            raise ValidationError(_('Call is no longer ringing.'))
        self.write({
            'state': 'connected',
            'started_at': fields.Datetime.now(),
        })

    def action_add_participant(self, user_id):
        self.ensure_one()
        if self.room_type != 'group':
            raise ValidationError(_('Participants can only be added to group rooms.'))
        if len(self.participant_ids) >= self.max_participants:
            raise ValidationError(_('Room is full (max %(max)s).', max=self.max_participants))
        self.write({'participant_ids': [(4, user_id)]})
        # Notify new participant
        user = self.env['res.users'].browse(user_id)
        self.env['bus.bus']._sendone(
            user.partner_id,
            'social_calling/room_invite',
            {
                'session_id': self.id,
                'room_name': self.name,
                'host_name': self.host_id.name,
                'room_url': '/my/calls/room/%s' % self.id,
            }
        )

    def action_remove_participant(self, user_id):
        self.ensure_one()
        if self.room_type != 'group':
            raise ValidationError(_('Participants can only be removed from group rooms.'))
        self.write({'participant_ids': [(3, user_id)]})
        if not self.participant_ids:
            self.action_end()

    def action_end(self):
        self.ensure_one()
        if self.state not in ('ringing', 'connected'):
            return
        self.write({
            'state': 'ended',
            'ended_at': fields.Datetime.now(),
        })

    def action_decline(self):
        self.ensure_one()
        if self.state != 'ringing':
            return
        self.write({'state': 'declined'})

    def action_mark_missed(self):
        self.ensure_one()
        if self.state == 'ringing':
            self.write({'state': 'missed'})
            # Notifie le destinataire qu'il a manqué l'appel (cloche + bus).
            if self.room_type == 'direct' and self.callee_id and self.caller_id:
                self.env['club_social_profile.notification']._notify(
                    user_id=self.callee_id.id,
                    actor_id=self.caller_id.id,
                    notif_type='missed_call',
                    body=_('Appel manqué de %s') % self.caller_id.name,
                    url='/profile/%s' % self.caller_id.id,
                )

    @api.model
    def cron_mark_missed_calls(self):
        cutoff = fields.Datetime.add(fields.Datetime.now(), minutes=-2)
        missed = self.search([
            ('state', '=', 'ringing'),
            ('create_date', '<', cutoff),
        ])
        for call in missed:
            call.action_mark_missed()
        return len(missed)

    @api.model
    def cron_purge_old_calls(self):
        """Rétention Loi 25 : supprime les appels, leur transcript et les
        fichiers uploadés au-delà de `social_calling.retention_days` (défaut
        90 jours ; 0 = rétention illimitée)."""
        days = int(self.env['ir.config_parameter'].sudo().get_str(
            'social_calling.retention_days', 90) or 90)
        if days <= 0:
            return 0
        cutoff = fields.Datetime.add(fields.Datetime.now(), days=-days)
        old = self.search([('create_date', '<', cutoff)])
        if not old:
            return 0
        # Les ir.attachment ne sont pas supprimés par la cascade du message :
        # on les retire explicitement du filestore.
        atts = self.env['ir.attachment'].sudo().search([
            ('res_model', '=', 'social_calling.session'),
            ('res_id', 'in', old.ids),
        ])
        count = len(old)
        old.unlink()      # cascade -> social_calling.message
        atts.exists().unlink()     # fichiers (déjà retirés par la cascade en 20)
        return count
