from odoo import api, fields, models


class ClubSocialNotification(models.Model):
    _inherit = 'club_social_profile.notification'

    type = fields.Selection(selection_add=[
        ('event_registration', 'Event registration'),
        ('group_join_request', 'Group join request'),
        ('group_join_approved', 'Membership approved'),
        ('proposal_voting', 'Proposal open for voting'),
        ('story_new', 'New story'),
        ('gallery_photo_approved', 'Photo approved in a gallery'),
        ('gallery_photo_rejected', 'Photo rejected'),
        ('vouching_received', 'Vouch received'),
        ('vouching_withdrawn', 'Vouch withdrawn'),
        ('negotiation_shared', 'Negotiation document shared'),
        ('negotiation_signed', 'Negotiation document signed'),
        ('negotiation_active', 'Negotiation document active'),
        ('circle_added', 'Added to a circle'),
    ], ondelete={
        'event_registration': 'cascade',
        'group_join_request': 'cascade',
        'group_join_approved': 'cascade',
        'proposal_voting': 'cascade',
        'story_new': 'cascade',
        'gallery_photo_approved': 'cascade',
        'gallery_photo_rejected': 'cascade',
        'vouching_received': 'cascade',
        'vouching_withdrawn': 'cascade',
        'negotiation_shared': 'cascade',
        'negotiation_signed': 'cascade',
        'negotiation_active': 'cascade',
        'circle_added': 'cascade',
    })

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for notif in records.filtered(lambda n: n.user_id.partner_id):
            self.env['bus.bus']._sendone(
                notif.user_id.partner_id,
                'social_notification',
                {
                    'id': notif.id,
                    'type': notif.type,
                    'body': notif.body,
                    'url': notif.url or False,
                },
            )
        return records
