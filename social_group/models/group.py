from datetime import timedelta

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class SocialGroup(models.Model):
    _name = 'social_group.group'
    _description = 'Social Group'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name asc'

    name = fields.Char('Group Name', required=True, translate=True)
    description = fields.Text('Description', translate=True)
    image = fields.Binary('Group Image')
    cover_image = fields.Binary('Cover Image')
    create_date = fields.Datetime('Created', readonly=True)
    creator_id = fields.Many2one('res.users', 'Created By', required=True, default=lambda self: self.env.user)

    member_ids = fields.Many2many('res.users', 'social_group_member_rel', 'group_id', 'user_id', string='Members')
    member_count = fields.Integer('Members', compute='_compute_member_count', store=True)
    admin_ids = fields.Many2many('res.users', 'social_group_admin_rel', 'group_id', 'user_id', string='Administrators')
    moderated_by = fields.Many2many('res.users', 'social_group_moderator_rel', 'group_id', 'user_id', string='Moderators')

    # Canal Discuss du groupe : l'espace de discussion du groupe (privé aux
    # membres). Créé à la création du groupe, membres synchronisés avec member_ids.
    discuss_channel_id = fields.Many2one(
        'discuss.channel', string='Group Channel', ondelete='set null', copy=False)

    privacy = fields.Selection([
        ('public', 'Public'),
        ('private', 'Private'),
        ('secret', 'Secret'),
    ], default='private', required=True,
        help="Public: Anyone can see and join\nPrivate: Visible to all, join by approval\nSecret: Members only")

    join_type = fields.Selection([
        ('open', 'Open'),
        ('approval', 'Approval Required'),
        ('invite', 'Invite Only'),
    ], default='approval', required=True)

    require_moderation = fields.Boolean('Require Post Moderation', default=False)

    post_ids = fields.One2many('social_base.post', 'group_id', 'Posts')
    post_count = fields.Integer('Posts', compute='_compute_post_count', store=True)

    rule_ids = fields.One2many('social_group.rule', 'group_id', 'Rules')
    join_request_ids = fields.One2many('social_group.join_request', 'group_id', 'Join Requests')

    # ── Canal Discuss du groupe ──────────────────────────────────────────────

    @api.model_create_multi
    def create(self, vals_list):
        groups = super().create(vals_list)
        for group in groups:
            group._get_or_create_discuss_channel()
        return groups

    def write(self, vals):
        res = super().write(vals)
        if 'member_ids' in vals:
            for group in self:
                group._sync_channel_members()
        if 'name' in vals:
            for group in self:
                if group.discuss_channel_id:
                    group.discuss_channel_id.sudo().name = group.name
        return res

    def _get_or_create_discuss_channel(self):
        """Canal Discuss de groupe (privé aux membres). sudo : les utilisateurs
        portail ne peuvent pas créer de discuss.channel ; sudo garde env.user."""
        self.ensure_one()
        if self.discuss_channel_id:
            return self.discuss_channel_id
        Channel = self.env['discuss.channel'].sudo()
        channel = Channel.create({
            'name': self.name or _('Group'),
            'channel_type': 'group',
        })
        partners = self.member_ids.partner_id
        if partners:
            channel._add_members(partners=partners)
        self.sudo().discuss_channel_id = channel
        return channel

    def _sync_channel_members(self):
        """Aligne les membres du canal sur member_ids (ajout/retrait)."""
        self.ensure_one()
        channel = self.discuss_channel_id.sudo()
        if not channel:
            channel = self._get_or_create_discuss_channel()
            return
        desired = self.member_ids.partner_id
        current = channel.channel_member_ids.partner_id
        to_add = desired - current
        to_remove = current - desired
        if to_add:
            channel._add_members(partners=to_add)
        if to_remove:
            channel.channel_member_ids.filtered(
                lambda m: m.partner_id in to_remove).unlink()

    @api.depends('member_ids')
    def _compute_member_count(self):
        for group in self:
            group.member_count = len(group.member_ids)

    @api.depends('post_ids')
    def _compute_post_count(self):
        for group in self:
            group.post_count = len(group.post_ids)

    def action_join(self):
        self.ensure_one()
        if self.join_type == 'invite':
            raise ValidationError(_('This group is invite only'))

        if self.join_type == 'approval':
            self.env['social_group.join_request'].sudo().create({
                'group_id': self.id,
                'user_id': self.env.user.id,
            })
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {'title': _('Request Sent'), 'message': _('Your join request has been submitted.'), 'type': 'info'},
            }

        self.sudo().write({'member_ids': [(4, self.env.user.id)]})
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {'title': _('Joined'), 'message': _('You have joined the group.'), 'type': 'success'},
        }

    def action_leave(self):
        self.ensure_one()
        if self.env.user in self.admin_ids and len(self.admin_ids) == 1:
            raise ValidationError(_('You cannot leave as the only administrator'))
        self.sudo().write({'member_ids': [(3, self.env.user.id)]})

    def is_member(self, user):
        self.ensure_one()
        return user in self.member_ids

    def is_admin(self, user):
        self.ensure_one()
        return user in self.admin_ids

    def is_moderator(self, user):
        self.ensure_one()
        return user in self.moderated_by or user in self.admin_ids or user == self.creator_id


class SocialGroupRule(models.Model):
    _name = 'social_group.rule'
    _description = 'Group Rule'
    _order = 'sequence asc, id asc'

    group_id = fields.Many2one('social_group.group', 'Group', required=True, ondelete='cascade')
    name = fields.Char('Rule', required=True)
    description = fields.Text('Description')
    sequence = fields.Integer('Sequence', default=10)


class SocialGroupJoinRequest(models.Model):
    _name = 'social_group.join_request'
    _description = 'Group Join Request'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc'

    group_id = fields.Many2one('social_group.group', 'Group', required=True, ondelete='cascade')
    user_id = fields.Many2one('res.users', 'User', required=True, default=lambda self: self.env.user)
    create_date = fields.Datetime('Requested', readonly=True)
    state = fields.Selection([
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ], default='pending', required=True)
    processed_by = fields.Many2one('res.users', 'Processed By')
    processed_date = fields.Datetime('Processed Date')
    rejection_reason = fields.Text('Rejection Reason')

    def action_approve(self):
        self.ensure_one()
        self.group_id.sudo().write({'member_ids': [(4, self.user_id.id)]})
        self.sudo().write({
            'state': 'approved',
            'processed_by': self.env.user.id,
            'processed_date': fields.Datetime.now(),
        })

    def action_reject(self):
        self.ensure_one()
        self.sudo().write({
            'state': 'rejected',
            'processed_by': self.env.user.id,
            'processed_date': fields.Datetime.now(),
        })

    @api.model
    def cron_cleanup_old_requests(self):
        cutoff = fields.Datetime.now() - timedelta(days=30)
        old = self.search([('state', 'in', ['approved', 'rejected']), ('processed_date', '<', cutoff)])
        count = len(old)
        old.unlink()
        return count
