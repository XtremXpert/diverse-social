from datetime import timedelta

from odoo import models, fields, api


class SocialStory(models.Model):
    _name = 'social_story.story'
    _description = 'Social Story'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'club.visibility.mixin']
    _order = 'create_date desc'

    name = fields.Char('Title', required=True)
    author_id = fields.Many2one('res.users', 'Author', required=True, default=lambda self: self.env.user)
    create_date = fields.Datetime('Created', readonly=True)
    expires_at = fields.Datetime('Expires At', compute='_compute_expires_at', store=True, index=True)

    attachment_ids = fields.One2many(
        'ir.attachment', 'res_id',
        domain=[('res_model', '=', 'social_story.story')],
        string='Media',
    )
    media_type = fields.Selection([
        ('photo', 'Photo'),
        ('video', 'Video'),
    ], default='photo', compute='_compute_media_type', store=True, readonly=False)

    view_count = fields.Integer('Views', default=0)
    viewer_ids = fields.Many2many('res.users', 'social_story_view_rel', 'story_id', 'user_id', string='Viewers')
    reaction_ids = fields.One2many('social_base.reaction', 'story_id', 'Reactions')

    state = fields.Selection([
        ('active', 'Active'),
        ('expired', 'Expired'),
        ('archived', 'Archived'),
    ], compute='_compute_state', store=True, index=True)

    @api.depends('create_date')
    def _compute_expires_at(self):
        for story in self:
            base = story.create_date or fields.Datetime.now()
            story.expires_at = base + timedelta(hours=24)

    @api.depends('expires_at')
    def _compute_state(self):
        now = fields.Datetime.now()
        for story in self:
            if story.expires_at and story.expires_at < now:
                story.state = 'expired'
            else:
                story.state = 'active'

    @api.depends('attachment_ids', 'attachment_ids.mimetype')
    def _compute_media_type(self):
        for story in self:
            att = story.attachment_ids[:1]
            if att and att.mimetype:
                story.media_type = 'video' if att.mimetype.startswith('video/') else 'photo'
            else:
                story.media_type = 'photo'

    def _visibility_owner_partner(self):
        self.ensure_one()
        return self.author_id.partner_id

    def is_accessible_by(self, user):
        """Helper accepting res.users or res.partner."""
        self.ensure_one()
        partner = user.partner_id if hasattr(user, 'partner_id') else user
        return self._is_accessible_by(partner)

    def mark_as_viewed(self, user):
        self.ensure_one()
        if user not in self.viewer_ids:
            self.write({'viewer_ids': [(4, user.id)], 'view_count': self.view_count + 1})

    def action_archive(self):
        self.write({'state': 'archived'})

    @api.model
    def cron_cleanup_expired_stories(self):
        now = fields.Datetime.now()
        # `state` is a store=True compute on `expires_at`, but `expires_at`
        # is itself a compute on `create_date` (immutable post-creation).
        # Nothing ever rewrites either field, so the ORM never re-runs the
        # compute and no story transitions active→expired on its own. The
        # cron has to flip the state explicitly.
        self.env.cr.execute("""
            UPDATE social_story_story SET state = 'expired'
            WHERE state = 'active' AND expires_at < %s
            RETURNING id;
        """, (now,))
        expired_ids = [row[0] for row in self.env.cr.fetchall()]
        if expired_ids:
            self.browse(expired_ids).invalidate_recordset(['state'])
        cutoff = now - timedelta(days=7)
        expired = self.search([('state', '=', 'expired'), ('expires_at', '<', cutoff)])
        count = len(expired)
        expired.unlink()
        return count
