from odoo import models, fields, api


class SocialReaction(models.Model):
    _name = 'social_base.reaction'
    _description = 'Social Reaction'
    _order = 'create_date desc'

    post_id = fields.Many2one('social_base.post', 'Post', ondelete='cascade', index=True)
    comment_id = fields.Many2one('social_base.comment', 'Comment', ondelete='cascade', index=True)

    type = fields.Selection([
        ('like', '👍 Like'),
        ('love', '❤️ Love'),
        ('laugh', '😂 Laugh'),
        ('wow', '😮 Wow'),
        ('sad', '😢 Sad'),
        ('angry', '😠 Angry'),
        ('celebrate', '🎉 Celebrate'),
        ('support', '💪 Support'),
    ], string='Reaction Type', required=True)

    user_id = fields.Many2one('res.users', 'User', required=True, default=lambda self: self.env.user, index=True)
    create_date = fields.Datetime('Reacted', readonly=True)

    target_id = fields.Integer('Target ID', compute='_compute_target', store=True)
    target_model = fields.Char('Target Model', compute='_compute_target', store=True)

    @api.depends('post_id', 'comment_id')
    def _compute_target(self):
        for reaction in self:
            if reaction.post_id:
                reaction.target_id = reaction.post_id.id
                reaction.target_model = 'social_base.post'
            elif reaction.comment_id:
                reaction.target_id = reaction.comment_id.id
                reaction.target_model = 'social_base.comment'
            else:
                reaction.target_id = 0
                reaction.target_model = False

    @api.model_create_multi
    def create(self, vals_list):
        """Pre-load existing reactions in batch (avoid N+1) before create."""
        post_keys = {}
        comment_keys = {}
        no_target = []

        for vals in vals_list:
            uid = vals.get('user_id', self.env.user.id)
            if vals.get('post_id'):
                post_keys[(uid, vals['post_id'])] = vals
            elif vals.get('comment_id'):
                comment_keys[(uid, vals['comment_id'])] = vals
            else:
                no_target.append(vals)

        existing_map = {}

        if post_keys:
            user_ids = [k[0] for k in post_keys]
            post_ids = [k[1] for k in post_keys]
            for r in self.search([('user_id', 'in', user_ids), ('post_id', 'in', post_ids)]):
                existing_map[('post_id', r.post_id.id, r.user_id.id)] = r

        if comment_keys:
            user_ids = [k[0] for k in comment_keys]
            comment_ids = [k[1] for k in comment_keys]
            for r in self.search([('user_id', 'in', user_ids), ('comment_id', 'in', comment_ids)]):
                existing_map[('comment_id', r.comment_id.id, r.user_id.id)] = r

        result = self.env['social_base.reaction']
        to_create = list(no_target)

        for (uid, target_id), vals in list(post_keys.items()) + list(comment_keys.items()):
            if vals.get('post_id'):
                key = ('post_id', target_id, uid)
            else:
                key = ('comment_id', target_id, uid)

            existing = existing_map.get(key)
            if existing:
                existing.write({'type': vals.get('type', existing.type)})
                result |= existing
            else:
                to_create.append(vals)

        if to_create:
            result |= super().create(to_create)

        return result

    def toggle_reaction(self, reaction_type):
        self.ensure_one()
        if self.type == reaction_type:
            self.unlink()
        else:
            self.write({'type': reaction_type})
