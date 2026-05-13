from odoo import _, models


class SocialGalleryPhotoNotification(models.Model):
    _inherit = 'social_gallery.photo'

    def action_approve(self):
        res = super().action_approve()
        Notif = self.env['club_social_profile.notification']
        for photo in self.filtered('submitted_by_id'):
            Notif._notify(
                user_id=photo.submitted_by_id.id,
                actor_id=self.env.user.id,
                notif_type='gallery_photo_approved',
                body=_('Votre photo « %s » a été approuvée dans la galerie « %s ».',
                        photo.name or _('sans titre'), photo.gallery_id.name),
                ref_model='social_gallery.photo',
                ref_id=photo.id,
            )
        return res

    def action_reject(self):
        res = super().action_reject()
        Notif = self.env['club_social_profile.notification']
        for photo in self.filtered('submitted_by_id'):
            Notif._notify(
                user_id=photo.submitted_by_id.id,
                actor_id=self.env.user.id,
                notif_type='gallery_photo_rejected',
                body=_('Votre photo « %s » a été rejetée.', photo.name or _('sans titre')),
                ref_model='social_gallery.photo',
                ref_id=photo.id,
            )
        return res
