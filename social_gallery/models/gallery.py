from odoo import api, fields, models


class SocialGallery(models.Model):
    _name = 'social_gallery.gallery'
    _description = 'Social Gallery'
    _inherit = ['club.visibility.mixin']
    _order = 'sequence, id'

    name = fields.Char('Title', required=True)
    description = fields.Text('Description')
    owner_id = fields.Many2one('res.users', 'Owner', ondelete='cascade', index=True)
    sequence = fields.Integer(default=10)
    is_shared = fields.Boolean(
        'Shared Gallery',
        default=False,
        help='Shared galleries accept submissions from all members.',
    )

    photo_ids = fields.One2many('social_gallery.photo', 'gallery_id', 'Photos')
    photo_count = fields.Integer(compute='_compute_photo_count', store=True)
    approved_photo_count = fields.Integer(compute='_compute_photo_count', store=True)
    pending_photo_count = fields.Integer(compute='_compute_photo_count', store=True)

    cover_photo_id = fields.Many2one(
        'social_gallery.photo', 'Cover Photo',
        domain="[('gallery_id', '=', id), ('state', '=', 'approved'), ('media_type', '=', 'image')]",
        ondelete='set null',
    )

    @api.depends('photo_ids', 'photo_ids.state')
    def _compute_photo_count(self):
        for gallery in self:
            gallery.photo_count = len(gallery.photo_ids)
            gallery.approved_photo_count = len(gallery.photo_ids.filtered(lambda p: p.state == 'approved'))
            gallery.pending_photo_count = len(gallery.photo_ids.filtered(lambda p: p.state == 'pending'))

    def _visibility_owner_partner(self):
        self.ensure_one()
        return self.owner_id.partner_id

    def is_accessible_by(self, user):
        """Helper accepting res.users or res.partner."""
        self.ensure_one()
        partner = user.partner_id if hasattr(user, 'partner_id') else user
        return self._is_accessible_by(partner)


class SocialGalleryPhoto(models.Model):
    _name = 'social_gallery.photo'
    _description = 'Gallery Photo'
    _order = 'sequence, id'

    gallery_id = fields.Many2one(
        'social_gallery.gallery', 'Gallery', required=True, ondelete='cascade', index=True,
    )
    name = fields.Char('Title')
    description = fields.Text('Description')
    sequence = fields.Integer(default=10)

    media_type = fields.Selection([
        ('image', 'Image'),
        ('video', 'Video'),
    ], default='image', required=True, index=True)

    image_1920 = fields.Image('Photo', max_width=1920, max_height=1920)
    image_512 = fields.Image('Thumbnail', related='image_1920', max_width=512, max_height=512, store=True)

    # Vidéo stockée dans le filestore (attachment=True) → adapté aux gros fichiers
    # (jusqu'à 25 Mo) sans gonfler la base. Servie via /web/content (l'ir.rule de
    # la photo régit l'accès en lecture).
    video_file = fields.Binary('Video', attachment=True)
    video_filename = fields.Char('Video Filename')

    state = fields.Selection([
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ], default='approved', required=True, index=True)
    submitted_by_id = fields.Many2one('res.users', 'Submitted By', ondelete='set null', index=True)
    moderated_by_id = fields.Many2one('res.users', 'Moderated By', ondelete='set null')
    moderation_date = fields.Datetime('Moderation Date')

    def action_approve(self):
        self.write({
            'state': 'approved',
            'moderated_by_id': self.env.user.id,
            'moderation_date': fields.Datetime.now(),
        })

    def action_reject(self):
        self.write({
            'state': 'rejected',
            'moderated_by_id': self.env.user.id,
            'moderation_date': fields.Datetime.now(),
        })
