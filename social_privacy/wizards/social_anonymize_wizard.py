from odoo import models, fields, api, _
from odoo.exceptions import UserError


class SocialAnonymizeWizard(models.TransientModel):
    _name = 'social_privacy.anonymize_wizard'
    _description = 'Social Profile Anonymization Wizard'

    partner_id = fields.Many2one('res.partner', string='Partner', required=True)
    user_id = fields.Many2one(
        'res.users',
        string='Related User',
        compute='_compute_user',
        store=True,
    )

    # Counts for confirmation display
    post_count = fields.Integer(compute='_compute_counts')
    comment_count = fields.Integer(compute='_compute_counts')
    message_count = fields.Integer(compute='_compute_counts')
    negotiation_count = fields.Integer(compute='_compute_counts')
    vote_count = fields.Integer(compute='_compute_counts')
    vouching_given = fields.Integer(compute='_compute_counts')
    vouching_received = fields.Integer(compute='_compute_counts')
    notification_count = fields.Integer(compute='_compute_counts')
    gallery_photo_count = fields.Integer(compute='_compute_counts')
    story_count = fields.Integer(compute='_compute_counts')
    profile_visit_count = fields.Integer(compute='_compute_counts')

    confirm_understand = fields.Boolean(
        string='I understand this action is irreversible',
        required=True,
        default=False,
    )

    def _anonymous_user(self):
        return self.env.ref('social_privacy.user_anonymous').sudo()

    @api.depends('partner_id')
    def _compute_user(self):
        for wiz in self:
            users = self.env['res.users'].sudo().search(
                [('partner_id', '=', wiz.partner_id.id)]
            )
            wiz.user_id = users[:1] if users else False

    @api.depends('user_id')
    def _compute_counts(self):
        for wiz in self:
            user = wiz.user_id
            if not user:
                wiz.post_count = 0
                wiz.comment_count = 0
                wiz.message_count = 0
                wiz.negotiation_count = 0
                wiz.vote_count = 0
                wiz.vouching_given = 0
                wiz.vouching_received = 0
                wiz.notification_count = 0
                wiz.gallery_photo_count = 0
                wiz.story_count = 0
                wiz.profile_visit_count = 0
                continue

            wiz.post_count = self.env['social_base.post'].sudo().search_count(
                [('author_id', '=', user.id)]
            )
            wiz.comment_count = self.env['social_base.comment'].sudo().search_count(
                [('author_id', '=', user.id)]
            )
            wiz.message_count = self.env['social_messaging.message'].sudo().search_count(
                [('author_id', '=', user.id)]
            )
            if 'social_negotiation.negotiation' in self.env:
                wiz.negotiation_count = self.env['social_negotiation.negotiation'].sudo().search_count(
                    ['|', ('initiator_id', '=', user.id), ('partner_id', '=', user.id)]
                )
            else:
                wiz.negotiation_count = 0
            wiz.vote_count = self.env['social_governance.vote'].sudo().search_count(
                [('voter_id', '=', user.id)]
            )
            wiz.vouching_given = self.env['social_reputation.vouching'].sudo().search_count(
                [('sponsor_id', '=', user.id)]
            )
            wiz.vouching_received = self.env['social_reputation.vouching'].sudo().search_count(
                [('newcomer_id', '=', user.id)]
            )
            wiz.notification_count = self.env['club_social_profile.notification'].sudo().search_count(
                [('user_id', '=', user.id)]
            )
            wiz.gallery_photo_count = self.env['social_gallery.photo'].sudo().search_count(
                [('submitted_by_id', '=', user.id)]
            )
            wiz.story_count = self.env['social_story.story'].sudo().search_count(
                [('author_id', '=', user.id)]
            )
            wiz.profile_visit_count = self.env['club_social_profile.profile_visit'].sudo().search_count(
                [('visitor_id', '=', user.id)]
            )

    def action_anonymize(self):
        self.ensure_one()
        if not self.confirm_understand:
            raise UserError(_('You must confirm you understand this is irreversible.'))

        partner = self.partner_id
        user = self.user_id
        if not user:
            raise UserError(_('No user found for this partner.'))

        # 1. Trigger OCA partner anonymization if available
        # privacy_partner_to_be_forgotten adds an action on res.partner
        try:
            partner.action_anonymize()
        except AttributeError:
            # Fallback: mark as anonymized manually if OCA method not present
            partner.write({
                'is_anonymized': True,
                'anonymization_date': fields.Datetime.now(),
            })

        # 2. Anonymize / delete social data
        self._anonymize_posts(user)
        self._anonymize_comments(user)
        self._anonymize_messages(user)
        self._anonymize_negotiations(user)
        self._anonymize_votes(user)
        self._anonymize_vouchings(user)
        self._anonymize_profile_visits(user)
        self._anonymize_notifications(user)
        self._anonymize_safety_records(user)
        self._anonymize_circles(user)
        self._anonymize_gallery_photos(user)
        self._anonymize_stories(user)
        self._anonymize_consent_requests(user)
        self._anonymize_group_memberships(user)
        self._anonymize_event_registrations(user)
        self._anonymize_connections(user)
        self._anonymize_discoveries(user)
        self._anonymize_privacy_consents(user)

        # 3. Anonymize the social profile itself
        profile = self.env['club_social_profile.profile'].sudo().search(
            [('user_id', '=', user.id)], limit=1
        )
        if profile:
            profile.write({
                'pronouns': False,
                'bio': False,
                'quote': False,
                'city': False,
                'region': False,
                'birth_year': 0,
                'gender': False,
                'orientation': False,
                'availability': False,
                'profile_image': False,
                'cover_image': False,
                'stealth_name': False,
                'onboarding_done': False,
                'age_verified': False,
            })

        # 4. Log the anonymization
        self.env['social_privacy.access_log'].sudo().create({
            'user_id': self.env.user.id,
            'target_user_id': user.id,
            'model_name': 'res.users',
            'record_id': user.id,
            'action': 'anonymize',
            'reason': 'Right to be forgotten / Droit a l oubli',
        })

        self.env['social_privacy.anonymize_log'].sudo().action_log_anonymization(
            partner, user, 'done',
            'Full social anonymization completed.',
        )

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Anonymization Complete'),
                'message': _('User data has been anonymized or deleted.'),
                'type': 'success',
                'sticky': False,
            },
        }

    # --- Anonymization helpers ---

    def _anonymize_posts(self, user):
        Post = self.env['social_base.post'].sudo()
        anonymous_id = self._anonymous_user().id
        posts = Post.search([('author_id', '=', user.id)])
        for post in posts:
            post.write({
                'author_id': anonymous_id,
                'content': '[Content anonymized]',
                'state': 'archived',
            })

    def _anonymize_comments(self, user):
        Comment = self.env['social_base.comment'].sudo()
        anonymous_id = self._anonymous_user().id
        comments = Comment.search([('author_id', '=', user.id)])
        for comment in comments:
            comment.write({
                'author_id': anonymous_id,
                'content': '[Comment anonymized]',
                'state': 'deleted',
            })

    def _anonymize_messages(self, user):
        Message = self.env['social_messaging.message'].sudo()
        msgs = Message.search([('author_id', '=', user.id)])
        # Private messages are fully deleted (most sensitive)
        msgs.unlink()

    def _anonymize_negotiations(self, user):
        if 'social_negotiation.negotiation' not in self.env:
            return
        Neg = self.env['social_negotiation.negotiation'].sudo()
        anonymous_id = self._anonymous_user().id
        negs = Neg.search([
            '|', ('initiator_id', '=', user.id), ('partner_id', '=', user.id)
        ])
        for neg in negs:
            neg.action_archive()
            vals = {}
            if neg.initiator_id == user:
                vals['initiator_id'] = anonymous_id
            if neg.partner_id == user:
                vals['partner_id'] = anonymous_id
            neg.write(vals)

    def _anonymize_votes(self, user):
        Vote = self.env['social_governance.vote'].sudo()
        anonymous_id = self._anonymous_user().id
        votes = Vote.search([('voter_id', '=', user.id)])
        for vote in votes:
            # Keep the vote for governance integrity, anonymize voter
            vote.write({'voter_id': anonymous_id})

    def _anonymize_vouchings(self, user):
        Vouch = self.env['social_reputation.vouching'].sudo()
        given = Vouch.search([('sponsor_id', '=', user.id)])
        received = Vouch.search([('newcomer_id', '=', user.id)])
        given.unlink()
        received.unlink()

    def _anonymize_profile_visits(self, user):
        Visit = self.env['club_social_profile.profile_visit'].sudo()
        visits = Visit.search([('visitor_id', '=', user.id)])
        visits.unlink()

    def _anonymize_notifications(self, user):
        Notif = self.env['club_social_profile.notification'].sudo()
        notifs = Notif.search([('user_id', '=', user.id)])
        notifs.unlink()

    def _anonymize_safety_records(self, user):
        Block = self.env['social_safety.block'].sudo()
        Mute = self.env['social_safety.mute'].sudo()
        blocks = Block.search([
            '|', ('blocker_id', '=', user.id), ('blocked_id', '=', user.id)
        ])
        mutes = Mute.search([
            '|', ('muter_id', '=', user.id), ('muted_id', '=', user.id)
        ])
        blocks.unlink()
        mutes.unlink()

    def _anonymize_circles(self, user):
        Circle = self.env['social_circles.circle'].sudo()
        circles = Circle.search([('profile_id.user_id', '=', user.id)])
        circles.unlink()

    def _anonymize_gallery_photos(self, user):
        Photo = self.env['social_gallery.photo'].sudo()
        photos = Photo.search([('submitted_by_id', '=', user.id)])
        photos.unlink()

    def _anonymize_stories(self, user):
        Story = self.env['social_story.story'].sudo()
        stories = Story.search([('author_id', '=', user.id)])
        stories.unlink()

    def _anonymize_consent_requests(self, user):
        if 'social_consent.request' not in self.env:
            return
        Request = self.env['social_consent.request'].sudo()
        reqs = Request.search([('requester_id', '=', user.id)])
        reqs.unlink()

    def _anonymize_group_memberships(self, user):
        # Remove user from all groups (unlink from m2m)
        Group = self.env['social_group.group'].sudo()
        groups = Group.search([
            '|', ('member_ids', 'in', [user.id]), ('admin_ids', 'in', [user.id])
        ])
        for group in groups:
            group.write({
                'member_ids': [(3, user.id)],
                'admin_ids': [(3, user.id)],
                'moderated_by': [(3, user.id)],
            })
        # Delete pending join requests
        JoinReq = self.env['social_group.join_request'].sudo()
        JoinReq.search([('user_id', '=', user.id)]).unlink()

    def _anonymize_event_registrations(self, user):
        # Odoo event registrations are linked to partner, already anonymized by OCA
        pass

    def _anonymize_connections(self, user):
        Conn = self.env['club_social_profile.connection'].sudo()
        conns = Conn.search([
            '|', ('user_id', '=', user.id), ('connected_user_id', '=', user.id)
        ])
        conns.unlink()

    def _anonymize_discoveries(self, user):
        Criteria = self.env['social_discovery.criteria'].sudo()
        crits = Criteria.search([('profile_id.user_id', '=', user.id)])
        crits.unlink()

    def _anonymize_privacy_consents(self, user):
        Consent = self.env['social_privacy.consent'].sudo()
        consents = Consent.search([('user_id', '=', user.id)])
        # Withdraw all consents with reason before deletion
        for consent in consents:
            consent.action_withdraw('User account anonymized / Right to be forgotten')
        consents.unlink()
