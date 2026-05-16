from odoo import api, fields, models


class ClubSocialNotification(models.Model):
    _inherit = 'club_social_profile.notification'

    type = fields.Selection(selection_add=[
        ('event_registration', 'Inscription à un événement'),
        ('group_join_request', "Demande d'adhésion à un groupe"),
        ('group_join_approved', "Adhésion approuvée"),
        ('proposal_voting', 'Proposition ouverte au vote'),
        ('story_new', 'Nouvelle story'),
        ('gallery_photo_approved', 'Photo approuvée dans une galerie'),
        ('gallery_photo_rejected', 'Photo rejetée'),
        ('vouching_received', 'Parrainage reçu'),
        ('vouching_withdrawn', 'Parrainage retiré'),
        ('negotiation_shared', 'Document de négociation partagé'),
        ('negotiation_signed', 'Document de négociation signé'),
        ('negotiation_active', 'Document de négociation actif'),
        ('circle_added', 'Ajouté à un cercle'),
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
