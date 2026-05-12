import re

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class SocialPost(models.Model):
    _name = 'social_base.post'
    _description = 'Social Post'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc'

    name = fields.Char('Subject', default='Post')
    content = fields.Html('Content')
    author_id = fields.Many2one('res.users', 'Author', required=True, default=lambda self: self.env.user)
    create_date = fields.Datetime('Posted', readonly=True)

    attachment_ids = fields.One2many(
        'ir.attachment', 'res_id',
        domain=[('res_model', '=', 'social_base.post')],
        string='Attachments',
    )
    media_type = fields.Selection([
        ('text', 'Text Only'),
        ('photo', 'Photo'),
        ('video', 'Video'),
        ('mixed', 'Mixed Media'),
    ], compute='_compute_media_type', store=True)

    like_count = fields.Integer('Likes', compute='_compute_engagement', store=True)
    comment_count = fields.Integer('Comments', compute='_compute_engagement', store=True)
    reaction_ids = fields.One2many('social_base.reaction', 'post_id', 'Reactions')
    comment_ids = fields.One2many('social_base.comment', 'post_id', 'Comments')

    visibility = fields.Selection([
        ('public', 'Public'),
        ('members', 'Members Only'),
        ('friends', 'Friends Only'),
        ('private', 'Private'),
    ], default='members', required=True)

    is_pinned = fields.Boolean('Pinned')

    state = fields.Selection([
        ('draft', 'Draft'),
        ('published', 'Published'),
        ('archived', 'Archived'),
        ('moderation', 'Awaiting Moderation'),
    ], default='published', required=True)
    moderated_by = fields.Many2one('res.users', 'Moderated By')
    moderation_date = fields.Datetime('Moderation Date')
    moderation_reason = fields.Text('Moderation Reason')

    view_count = fields.Integer('Views', default=0)
    share_count = fields.Integer('Shares', default=0)

    @api.depends('attachment_ids', 'attachment_ids.mimetype')
    def _compute_media_type(self):
        for post in self:
            if not post.attachment_ids:
                post.media_type = 'text'
                continue
            has_photo = has_video = False
            for att in post.attachment_ids:
                if att.mimetype and att.mimetype.startswith('image/'):
                    has_photo = True
                elif att.mimetype and att.mimetype.startswith('video/'):
                    has_video = True
            if has_photo and has_video:
                post.media_type = 'mixed'
            elif has_photo:
                post.media_type = 'photo'
            elif has_video:
                post.media_type = 'video'
            else:
                post.media_type = 'text'

    @api.depends('reaction_ids.type', 'comment_ids')
    def _compute_engagement(self):
        for post in self:
            post.like_count = len(post.reaction_ids.filtered(lambda r: r.type == 'like'))
            post.comment_count = len(post.comment_ids)

    def action_publish(self):
        self.write({'state': 'published'})

    def action_archive(self):
        self.write({'state': 'archived'})

    def action_submit_moderation(self):
        self.write({'state': 'moderation'})

    def action_approve(self):
        self.write({
            'state': 'published',
            'moderated_by': self.env.user.id,
            'moderation_date': fields.Datetime.now(),
        })

    def action_reject(self, reason):
        self.write({
            'state': 'archived',
            'moderated_by': self.env.user.id,
            'moderation_date': fields.Datetime.now(),
            'moderation_reason': reason,
        })

    def increment_view_count(self):
        self.write({'view_count': self.view_count + 1})

    def increment_share_count(self):
        self.write({'share_count': self.share_count + 1})

    @api.constrains('content', 'attachment_ids')
    def _check_content_or_attachment(self):
        for post in self:
            clean = re.sub('<[^<]+?>', '', post.content or '').strip()
            if not clean and not post.attachment_ids:
                raise ValidationError(_('Post must have content or attachment'))
