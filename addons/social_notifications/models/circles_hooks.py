from odoo import _, models


class SocialCircleNotification(models.Model):
    _inherit = 'social_circles.circle'

    def add_member(self, user):
        was_member = user in self.member_ids
        super().add_member(user)
        if not was_member:
            self.env['club_social_profile.notification']._notify(
                user_id=user.id,
                actor_id=self.profile_id.user_id.id,
                notif_type='circle_added',
                body=_('%(name)s vous a ajouté à son cercle « %(circle)s ».',
                        name=self.profile_id.user_id.name, circle=self.name),
            )
