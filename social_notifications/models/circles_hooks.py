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
                body=_('%(name)s added you to their circle "%(circle)s".',
                        name=self.env['club_social_profile.profile']._display_name_for_user(self.profile_id.user_id),
                        circle=self.name),
            )
