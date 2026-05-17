from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class PrivacyBreach(models.Model):
    _name = 'social_privacy.breach'
    _description = 'Privacy Breach Incident'
    _order = 'discovery_date desc'
    _inherit = ['mail.thread']

    name = fields.Char(
        string='Incident ID',
        required=True,
        default=lambda s: s.env['ir.sequence'].next_by_code(
            'social_privacy.breach'
        ) or _('BREACH-???'),
    )
    discovery_date = fields.Datetime(
        string='Discovered On',
        required=True,
        default=fields.Datetime.now,
    )
    notification_date = fields.Datetime(
        string='CAI Notification Date',
    )
    severity = fields.Selection([
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
    ], string='Severity', required=True, default='low')
    description = fields.Text(string='Description', required=True)
    affected_user_ids = fields.Many2many(
        'res.users',
        'social_privacy_breach_user_rel',
        'breach_id', 'user_id',
        string='Affected Users',
    )
    affected_count = fields.Integer(
        string='Affected Count',
        compute='_compute_affected_count',
        store=True,
    )
    state = fields.Selection([
        ('detected', 'Detected'),
        ('investigating', 'Investigating'),
        ('notified_cai', 'CAI Notified'),
        ('notified_users', 'Users Notified'),
        ('resolved', 'Resolved'),
    ], string='Status', default='detected', required=True, tracking=True)

    # Loi 25: 72h notification pour incidents graves
    cai_notified_in_time = fields.Boolean(
        string='CAI Notified in Time',
        compute='_compute_cai_timely',
        store=True,
    )

    @api.depends('affected_user_ids')
    def _compute_affected_count(self):
        for breach in self:
            breach.affected_count = len(breach.affected_user_ids)

    @api.depends('discovery_date', 'notification_date', 'severity')
    def _compute_cai_timely(self):
        for breach in self:
            if not breach.notification_date:
                breach.cai_notified_in_time = False
                continue
            hours = (breach.notification_date - breach.discovery_date).total_seconds() / 3600
            breach.cai_notified_in_time = hours <= 72

    def action_investigate(self):
        self.write({'state': 'investigating'})

    def action_notify_cai(self):
        self.write({
            'state': 'notified_cai',
            'notification_date': fields.Datetime.now(),
        })

    def action_notify_users(self):
        for breach in self:
            for user in breach.affected_user_ids:
                if user.partner_id:
                    breach.message_post(
                        body=_(
                            'Privacy incident notification sent to %(user)s.',
                            user=user.name,
                        ),
                        message_type='notification',
                        subtype_xmlid='mail.mt_note',
                    )
        self.write({'state': 'notified_users'})

    def action_resolve(self):
        self.write({'state': 'resolved'})

    @api.constrains('notification_date', 'discovery_date')
    def _check_notification_after_discovery(self):
        for breach in self:
            if breach.notification_date and breach.discovery_date:
                if breach.notification_date < breach.discovery_date:
                    raise ValidationError(_(
                        'CAI notification date cannot be before discovery date.'
                    ))
