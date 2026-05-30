from odoo import fields, models


class SocialPost(models.Model):
    _inherit = 'social_base.post'

    category_id = fields.Many2one(
        'social_post_categories.category', string='Category',
        ondelete='set null', index=True,
        help="Optional — describes the intent of the post (e.g. annonce, "
             "alerte, question). Set via /social/api/posts using "
             "category_code (preferred) or category_id.",
    )
