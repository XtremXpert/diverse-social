from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class SocialComment(models.Model):
    _name = 'social_base.comment'
    _description = 'Social Comment'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date asc'

    content = fields.Text('Content', required=True)
    author_id = fields.Many2one('res.users', 'Author', required=True, default=lambda self: self.env.user)
    post_id = fields.Many2one('social_base.post', 'Post', required=True, ondelete='cascade', index=True)
    parent_id = fields.Many2one('social_base.comment', 'Parent Comment', ondelete='cascade', index=True)
    child_ids = fields.One2many('social_base.comment', 'parent_id', 'Replies')
    create_date = fields.Datetime('Posted', readonly=True)

    like_count = fields.Integer('Likes', compute='_compute_engagement', store=True)
    reaction_ids = fields.One2many('social_base.reaction', 'comment_id', 'Reactions')

    state = fields.Selection([
        ('published', 'Published'),
        ('hidden', 'Hidden'),
        ('deleted', 'Deleted'),
    ], default='published', required=True)
    moderated_by = fields.Many2one('res.users', 'Moderated By')
    moderation_date = fields.Datetime('Moderation Date')
    moderation_reason = fields.Text('Moderation Reason')

    @api.depends('reaction_ids.type')
    def _compute_engagement(self):
        for comment in self:
            comment.like_count = len(comment.reaction_ids.filtered(lambda r: r.type == 'like'))

    def action_hide(self):
        self.write({'state': 'hidden'})

    def action_delete(self):
        self.write({'state': 'deleted'})

    def action_restore(self):
        self.write({'state': 'published'})

    @api.constrains('parent_id')
    def _check_parent_id(self):
        for comment in self:
            if comment.parent_id and comment.parent_id.post_id != comment.post_id:
                raise ValidationError(_('Parent comment must belong to the same post'))
            if comment.parent_id:
                level = 0
                parent = comment.parent_id
                while parent:
                    level += 1
                    if level >= 3:
                        raise ValidationError(_('Maximum comment nesting level is 3'))
                    parent = parent.parent_id
